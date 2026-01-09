import os
import subprocess
from tempfile import TemporaryDirectory
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.utils.timezone import now

# --- Helper Functions ---

def format_currency(value):
    """
    Consistently rounds any numerical value to 2 decimal places.
    """
    if value is None:
        return Decimal('0.00')
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def tex_safe(text):
    """
    Escapes LaTeX special characters so they don't crash the compiler.
    """
    if text is None:
        return ""
    text = str(text)
    mapping = {
        '&': r'\&',
        '$': r'\$',
        '%': r'\%',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
        '\\': r'\textbackslash{}',
    }
    return "".join(mapping.get(c, c) for c in text)

# --- PDF Generation ---

def generate_invoice_pdf(invoice):
    """
    Generates a PDF using xelatex by pulling calculated totals 
    directly from the Invoice database fields.
    """
    profile = invoice.user.profile
    
    # Ensure totals are accurate before generating
    from .models import Invoice
    Invoice.objects.update_totals(invoice)
    invoice.refresh_from_db()

    # 1. Header & Client Context
    context = {
        'invoice': invoice,
        'company_name': tex_safe(profile.company_name),
        'vat_number': tex_safe(profile.vat_number),
        'tax_number': tex_safe(profile.tax_number),
        'vendor_number': tex_safe(profile.vendor_number),
        'invoice_number': tex_safe(invoice.number),
        'date_issued': invoice.date_issued,
        'due_date': invoice.due_date,
        'client_name': tex_safe(invoice.client.name),
        'bank_name': tex_safe(profile.bank_name),
        'account_holder': tex_safe(profile.account_holder),
        'account_number': tex_safe(profile.account_number),
        'branch_code': tex_safe(profile.branch_code),
    }

    # Billing Mode Setup
    is_service = invoice.billing_type == 'SERVICE'
    context['label_qty'] = "Hours" if is_service else "Qty"
    context['label_rate'] = "Rate" if is_service else "Unit Price"

    # Address Handling
    context['profile_address_safe'] = tex_safe(profile.address).replace('\n', r' \\ ')
    context['client_address_safe'] = tex_safe(invoice.client.address).replace('\n', r' \\ ')

    # 2. Financial Context
    context['subtotal'] = f"{invoice.subtotal_amount:,.2f}"
    context['vat_total'] = f"{invoice.tax_amount:,.2f}"
    context['grand_total'] = f"{invoice.total_amount:,.2f}"
    
    # FIX: Use vat_rate from UserProfile
    raw_vat_rate = getattr(profile, 'vat_rate', Decimal('15.00'))
    if raw_vat_rate is None:
        raw_vat_rate = Decimal('15.00')
    context['tax_rate'] = f"{raw_vat_rate:.0f}"

    # 3. Items List
    context['items'] = [
        {
            'description': tex_safe(item.description),
            'quantity': f"{item.quantity:.2f}" if is_service else f"{item.quantity:.0f}",
            'unit_price': f"{item.unit_price:,.2f}",
            'row_subtotal': f"{(item.quantity * item.unit_price):,.2f}"
        } for item in invoice.items.all()
    ]

    # 4. Render and Compile
    latex_content = render_to_string('invoices/latex/invoice_template.tex', context)

    with TemporaryDirectory() as tempdir:
        tex_file_path = os.path.join(tempdir, 'invoice.tex')
        with open(tex_file_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)

        result = subprocess.run(
            ['xelatex', '-interaction=nonstopmode', '-output-directory', tempdir, tex_file_path],
            capture_output=True,
            text=True,
            timeout=30
        )

        pdf_path = os.path.join(tempdir, 'invoice.pdf')
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                return f.read()
        else:
            print("LaTeX Output:", result.stdout)
            raise Exception(f"LaTeX failed to generate PDF. Check logs.")

# --- Email Functions ---

def email_invoice_to_client(invoice):
    """
    Standard email for sending out a new invoice.
    """
    try:
        pdf_bytes = generate_invoice_pdf(invoice)
        
        subject = f"Invoice {invoice.number} from {invoice.user.profile.company_name}"
        body = (f"Hi {invoice.client.name},\n\n"
                f"Please find attached invoice {invoice.number}.\n\n"
                f"Total Due: R {invoice.total_amount:,.2f}\n"
                f"Due Date: {invoice.due_date}\n\n"
                f"Regards,\n{invoice.user.profile.company_name}")
        
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[invoice.client.email],
        )
        
        filename = f"Invoice_{invoice.number or 'Draft'}.pdf"
        email.attach(filename, pdf_bytes, 'application/pdf')
        email.send()
        
        invoice.last_generated = now()
        invoice.save(update_fields=['last_generated'])
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

def email_receipt_to_client(invoice, amount_paid):
    """
    Sends a receipt email after a payment is recorded.
    """
    try:
        # Re-generate PDF which now includes the "PAID" stamp if balance is 0
        pdf_bytes = generate_invoice_pdf(invoice)
        
        subject = f"Payment Receipt: Invoice {invoice.number}"
        body = (
            f"Hi {invoice.client.name},\n\n"
            f"Thank you for your payment of R {amount_paid:,.2f}.\n\n"
            f"Your payment has been recorded against Invoice {invoice.number}. "
            f"Balance remaining: R {invoice.balance_due:,.2f}.\n\n"
            f"Please find the updated Tax Invoice attached.\n\n"
            f"Regards,\n{invoice.user.profile.company_name}"
        )
        
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[invoice.client.email],
        )
        
        filename = f"Receipt_{invoice.number}.pdf"
        email.attach(filename, pdf_bytes, 'application/pdf')
        email.send()
        return True
    except Exception as e:
        print(f"Receipt Email Error: {e}")
        return False