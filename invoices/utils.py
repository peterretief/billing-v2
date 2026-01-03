import os
import subprocess
import shutil
from tempfile import TemporaryDirectory
from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string

from django.core.mail import EmailMessage
from django.utils.timezone import now

# invoices/utils.py
from decimal import Decimal, ROUND_HALF_UP

def format_currency(value):
    """
    Consistently rounds any numerical value to 2 decimal places 
    for display in templates or statements.
    """
    if value is None:
        return Decimal('0.00')
    # Standardize to 2 decimal places
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def email_invoice_to_client(invoice):
    """
    Calls the PDF generator and sends an email to the client.
    """
    try:
        # 1. Generate the PDF bytes using your existing function
        pdf_bytes = generate_invoice_pdf(invoice)
        
        # 2. Build the email
        subject = f"Invoice {invoice.number} from {invoice.user.profile.company_name}"
        body = f"Hi {invoice.client.name},\n\nPlease find attached invoice {invoice.number}.\n\nTotal Due: R {invoice.total_amount:,.2f}\nDue Date: {invoice.due_date}\n\nRegards,\n{invoice.user.profile.company_name}"
        
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[invoice.client.email],
        )
        
        # 3. Attach the PDF
        filename = f"Invoice_{invoice.number or 'Draft'}.pdf"
        email.attach(filename, pdf_bytes, 'application/pdf')
        
        email.send()
        
        # 4. Optional: Update the 'last_generated' timestamp
        invoice.last_generated = now()
        invoice.save(update_fields=['last_generated'])
        
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False


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

def generate_invoice_pdf(invoice):
    """
    Generates a PDF using xelatex by pulling calculated totals 
    directly from the Invoice database fields.
    """
    # Access the profile from the custom User model
    profile = invoice.user.profile
    
    # Ensure totals are accurate before generating (Safety Check)
    # This prevents the PDF from showing 0 if the save signal hasn't finished
    from .models import Invoice
    Invoice.objects.update_totals(invoice)
    invoice.refresh_from_db()

    # 1. Header & Client Context
    context = {
        'invoice': invoice, # Passed to handle {% if invoice.tax_mode %}
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

    # Billing Mode Setup (Service vs Product)
    is_service = invoice.billing_type == 'SERVICE'
    context['label_qty'] = "Hours" if is_service else "Qty"
    context['label_rate'] = "Rate" if is_service else "Unit Price"

    # Address Handling (Replaces newlines with LaTeX line breaks)
    context['profile_address_safe'] = tex_safe(profile.address).replace('\n', r' \\ ')
    context['client_address_safe'] = tex_safe(invoice.client.address).replace('\n', r' \\ ')

    # 2. Financial Context
    # We pull these directly from the DB fields populated by your Manager
    context['subtotal'] = f"{invoice.subtotal_amount:,.2f}"
    context['vat_total'] = f"{invoice.tax_amount:,.2f}"
    context['grand_total'] = f"{invoice.total_amount:,.2f}"
    
    # Get tax rate as a simple integer for the label (e.g., "15")
    raw_tax_rate = profile.tax_rate if profile.tax_rate is not None else Decimal('15.00')
    context['tax_rate'] = f"{raw_tax_rate:.0f}"

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

        # Run xelatex
        # -interaction=nonstopmode prevents the process from hanging on errors
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
            # Logs the LaTeX error output so you can debug formatting issues
            print("LaTeX Output:", result.stdout)
            print("LaTeX Error:", result.stderr)
            raise Exception(f"LaTeX failed to generate PDF. Check logs.")