import os
import subprocess
from decimal import ROUND_HALF_UP, Decimal
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string
from django.utils.timezone import now

# --- Helper Functions ---

def format_currency(value):
    """Consistently rounds any numerical value to 2 decimal places."""
    if value is None:
        return Decimal('0.00')
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def tex_safe(text):
    """Escapes LaTeX special characters so they don't crash the compiler."""
    if text is None:
        return ""
    text = str(text)
    mapping = {
        '&': r'\&', '$': r'\$', '%': r'\%', '#': r'\#', '_': r'\_',
        '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}', '\\': r'\textbackslash{}',
    }
    return "".join(mapping.get(c, c) for c in text)

# --- PDF Generation ---

def generate_invoice_pdf(invoice, template_name='invoice_template.tex'):
    """
    Generates a PDF using xelatex. 
    Runs xelatex twice to ensure TikZ watermarks/layouts align correctly.
    """
    profile = invoice.user.profile
    
    # 1. Sync Data
    from .models import Invoice
    Invoice.objects.update_totals(invoice)
    invoice.refresh_from_db()

    # 2. Image Path Handling
    logo_path = ""
    if profile.logo and hasattr(profile.logo, 'path'):
        if os.path.exists(profile.logo.path):
            logo_path = profile.logo.path.replace('\\', '/')

    # 3. Context Building
    context = {
        'invoice': invoice,
        'currency': tex_safe(profile.currency), # ADDED THIS
        'logo_path': logo_path,
        'company_name': tex_safe(profile.company_name),
        'vat_number': tex_safe(profile.vat_number),
        'tax_number': tex_safe(profile.tax_number),
        'vendor_number': tex_safe(profile.vendor_number),
        'phone': tex_safe(profile.phone),
        'invoice_number': tex_safe(invoice.number),
        'date_issued': invoice.date_issued,
        'due_date': invoice.due_date,
        
        # Address logic: Uses salutation (Contact Name or Company) 
        # plus the formal Company Name if a contact exists.
        'client_name': tex_safe(invoice.client.salutation),
        'client_company': tex_safe(invoice.client.name) if invoice.client.contact_name else "",
        'client_vat_number': tex_safe(invoice.client.vat_number),
        'client_phone': tex_safe(invoice.client.phone),
        
        'bank_name': tex_safe(profile.bank_name),
        'account_holder': tex_safe(profile.account_holder),
        'account_number': tex_safe(profile.account_number),
        'branch_code': tex_safe(profile.branch_code),
        'swift_bic': tex_safe(profile.swift_bic),
    }

    # Billing Mode Setup
    is_service = invoice.billing_type == 'SERVICE'
    context['label_desc'] = "Description" if is_service else "Item"
    context['label_qty'] = "Hours" if is_service else "Units"
    context['label_rate'] = "Rate" if is_service else "Unit Price"

    # Address Handling
    context['profile_address_safe'] = tex_safe(profile.address).replace('\n', r' \\ ')
    context['client_address_safe'] = tex_safe(invoice.client.address).replace('\n', r' \\ ')

    # Financials
    context['subtotal'] = f"{invoice.subtotal_amount:,.2f}"
    context['vat_total'] = f"{invoice.tax_amount:,.2f}"
    context['grand_total'] = f"{invoice.total_amount:,.2f}"
    
    raw_vat_rate = getattr(profile, 'vat_rate', Decimal('15.00')) or Decimal('15.00')
    context['tax_rate'] = f"{raw_vat_rate:.0f}"

    # Item List Assembly
    items_list = []
    if hasattr(invoice, 'custominvoice'):
        for line in invoice.custominvoice.custom_lines.all():
            items_list.append({
                'description': tex_safe(line.description),
                'quantity': f"{line.quantity:.2f} {tex_safe(line.unit_label)}",
                'unit_price': f"{line.unit_price:,.2f}",
                'row_subtotal': f"{line.total:,.2f}"
            })
    else:
        for item in invoice.billed_items.all():
            items_list.append({
                'description': tex_safe(item.description),
                'quantity': f"{item.quantity:.2f}" if is_service else f"{item.quantity:.0f}",
                'unit_price': f"{item.unit_price:,.2f}",
                'row_subtotal': f"{(item.quantity * item.unit_price):,.2f}"
            })
    context['items'] = items_list

    # 4. Render and Compile
    latex_content = render_to_string(f"invoices/latex/{template_name}", context)

    with TemporaryDirectory() as tempdir:
        tex_file_path = os.path.join(tempdir, 'invoice.tex')
        with open(tex_file_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)

        # PASS 1: Generate auxiliary files
        subprocess.run(
            ['xelatex', '-interaction=nonstopmode', '-output-directory', tempdir, tex_file_path],
            capture_output=True, text=True, timeout=30
        )

        # PASS 2: Final PDF
        result = subprocess.run(
            ['xelatex', '-interaction=nonstopmode', '-output-directory', tempdir, tex_file_path],
            capture_output=True, text=True, timeout=30
        )

        pdf_path = os.path.join(tempdir, 'invoice.pdf')
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                return f.read()
        else:
            print("LaTeX Output:", result.stdout)
            raise Exception("LaTeX failed to generate PDF. Check logs.")


def render_invoice_tex(invoice, template_name='invoice_template.tex'):
    """Render LaTeX source for an invoice and return it as a string."""
    profile = invoice.user.profile
    from .models import Invoice
    Invoice.objects.update_totals(invoice)
    invoice.refresh_from_db()

    logo_path = ""
    if profile.logo and hasattr(profile.logo, 'path'):
        if os.path.exists(profile.logo.path):
            logo_path = profile.logo.path.replace('\\', '/')

    context = {
        'invoice': invoice,
        'logo_path': logo_path,
        'currency': tex_safe(profile.currency), # This is the "Bridge"
        'company_name': tex_safe(profile.company_name),
        'vat_number': tex_safe(profile.vat_number),
        'tax_number': tex_safe(profile.tax_number),
        'vendor_number': tex_safe(profile.vendor_number),
        'phone': tex_safe(profile.phone),
        'invoice_number': tex_safe(invoice.number),
        'date_issued': invoice.date_issued,
        'due_date': invoice.due_date,
        'client_name': tex_safe(invoice.client.salutation),

        'client_vat_number': tex_safe(invoice.client.vat_number),
        'client_phone': tex_safe(invoice.client.phone),
        'bank_name': tex_safe(profile.bank_name),
        'account_holder': tex_safe(profile.account_holder),
        'account_number': tex_safe(profile.account_number),
        'branch_code': tex_safe(profile.branch_code),
        'swift_bic': tex_safe(profile.swift_bic),
    }

    is_service = invoice.billing_type == 'SERVICE'
    context['label_desc'] = "Description" if is_service else "Item"
    context['label_qty'] = "Hours" if is_service else "Units"
    context['label_rate'] = "Rate" if is_service else "Unit Price"

    context['profile_address_safe'] = tex_safe(profile.address).replace('\n', r' \\\\ ')
    context['client_address_safe'] = tex_safe(invoice.client.address).replace('\n', r' \\\\ ')

    context['subtotal'] = f"{invoice.subtotal_amount:,.2f}"
    context['vat_total'] = f"{invoice.tax_amount:,.2f}"
    context['grand_total'] = f"{invoice.total_amount:,.2f}"

    raw_vat_rate = getattr(profile, 'vat_rate', Decimal('15.00')) or Decimal('15.00')
    context['tax_rate'] = f"{raw_vat_rate:.0f}"

    items_list = []
    if hasattr(invoice, 'custominvoice'):
        for line in invoice.custominvoice.custom_lines.all():
            items_list.append({
                'description': tex_safe(line.description),
                'quantity': f"{line.quantity:.2f} {tex_safe(line.unit_label)}",
                'unit_price': f"{line.unit_price:,.2f}",
                'row_subtotal': f"{line.total:,.2f}"
            })
    else:
        for item in invoice.billed_items.all():
            items_list.append({
                'description': tex_safe(item.description),
                'quantity': f"{item.quantity:.2f}" if is_service else f"{item.quantity:.0f}",
                'unit_price': f"{item.unit_price:,.2f}",
                'row_subtotal': f"{(item.quantity * item.unit_price):,.2f}"
            })
    context['items'] = items_list

    return render_to_string(f"invoices/latex/{template_name}", context)

# --- Email Functions ---

def email_invoice_to_client(invoice):
    """Standard method for sending out new invoices."""
    from .models import Invoice, InvoiceEmailStatusLog
    try:
        latex_source = render_invoice_tex(invoice)
        profile = invoice.user.profile
        invoice.latex_content = latex_source
        invoice.save(update_fields=['latex_content'])

        pdf_bytes = generate_invoice_pdf(invoice)

        friendly_from = f'"{profile.company_name}" <{settings.DEFAULT_FROM_EMAIL}>'
        reply_address = profile.business_email if profile.business_email else invoice.user.email

        subject = f"Invoice {invoice.number} from {profile.company_name}"
        
        # Personalized Greeting
        body = (f"Hi {invoice.client.salutation},\n\n"
                f"Please find attached invoice {invoice.number}.\n\n"
                f"Total Due: {profile.currency} {invoice.total_amount:,.2f}\n"
                f"Due Date: {invoice.due_date}\n\n"
                f"Regards,\n{profile.company_name}")

        email = EmailMessage(subject, body, friendly_from, [invoice.client.email], reply_to=[reply_address])
        email.attach(f"Invoice_{invoice.number or 'Draft'}.pdf", pdf_bytes, 'application/pdf')
        # Attach timesheet PDF if requested
        if invoice.attach_timesheet_to_email:
            from .utils import generate_timesheet_pdf
            timesheet_pdf = generate_timesheet_pdf(invoice)
            if timesheet_pdf:
                email.attach(f"Timesheet_{invoice.number or 'Draft'}.pdf", timesheet_pdf, 'application/pdf')

        backend = getattr(settings, 'INVOICE_EMAIL_BACKEND', None)
        if backend:
            conn = get_connection(backend=backend)

            email.connection = conn  # ← attach connection to the message
            email.send()             # ← use send() so Anymail populates anymail_status
            sent_messages = conn.send_messages([email])
        else:
            sent_messages = email.send()


        # Now anymail_status will actually be populated
        anymail_status = getattr(email, 'anymail_status', None)
        message_id = anymail_status.message_id if anymail_status else None

        print(f"DEBUG: Anymail Status Object: {anymail_status}")
        print(f"DEBUG: Captured Message ID: {message_id}")

        
        # Create the tracking record (One record only)
        InvoiceEmailStatusLog.objects.create(
            user=invoice.user,
            invoice=invoice,
            brevo_message_id=message_id,
            status="sent"
        )

        invoice.last_generated = now()
        invoice.status = Invoice.Status.PENDING
        invoice.save(update_fields=['last_generated', 'status'])
        return True
    except Exception as e:
        # This will catch if anymail_status is missing or DB fails
        print(f"Email Error: {e}")
        return False
    
    
def email_receipt_to_client(invoice, amount_paid):
    """Method for sending updated invoices as receipts."""
    try:
        latex_source = render_invoice_tex(invoice)
        profile = invoice.user.profile
        invoice.latex_content = latex_source
        invoice.save(update_fields=['latex_content'])

        pdf_bytes = generate_invoice_pdf(invoice)

        friendly_from = f'"{profile.company_name}" <{settings.DEFAULT_FROM_EMAIL}>'
        reply_address = profile.business_email if profile.business_email else invoice.user.email

        subject = f"Payment Receipt: Invoice {invoice.number}"
        
        # Personalized Greeting
        body = (f"Hi {invoice.client.salutation},\n\n"
                f"Thank you for your payment of {profile.currency} {amount_paid:,.2f}.\n\n"
                f"Balance remaining: {profile.currency} {invoice.balance_due:,.2f}.\n\n"
                f"Regards,\n{profile.company_name}")

        email = EmailMessage(subject, body, friendly_from, [invoice.client.email], reply_to=[reply_address])
        email.attach(f"Receipt_{invoice.number}.pdf", pdf_bytes, 'application/pdf')

        backend = getattr(settings, 'INVOICE_EMAIL_BACKEND', None)
        if backend:
            conn = get_connection(backend=backend)
            conn.send_messages([email])
        else:
            email.send()
        return True
    except Exception as e:
        print(f"Receipt Error: {e}")
        return False

def generate_timesheet_pdf(invoice):
    """
    Generates a PDF report of all timesheets billed to the invoice.
    Returns PDF bytes or None if no timesheets.
    """
    from timesheets.models import TimesheetEntry
    from django.template.loader import render_to_string
    from django.template import TemplateDoesNotExist
    from tempfile import TemporaryDirectory
    import os
    timesheets = invoice.billed_timesheets.all()
    if not timesheets:
        return None

    profile = invoice.user.profile
    total_hours = sum(ts.hours for ts in timesheets)
    total_value = sum(ts.total_value for ts in timesheets)

    context = {
        'invoice': invoice,
        'timesheets': timesheets,
        'total_hours': total_hours,
        'total_value': total_value,
        'profile': profile,
    }
    try:
        latex_content = render_to_string('timesheets/timesheet_report.tex', context)
    except TemplateDoesNotExist:
        return None
    with TemporaryDirectory() as tempdir:
        tex_file_path = os.path.join(tempdir, 'timesheet_report.tex')
        with open(tex_file_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        # Compile LaTeX
        import subprocess
        subprocess.run([
            'xelatex', '-interaction=nonstopmode', '-output-directory', tempdir, tex_file_path
        ], capture_output=True, text=True, timeout=30)
        pdf_path = os.path.join(tempdir, 'timesheet_report.pdf')
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                return f.read()
    return None