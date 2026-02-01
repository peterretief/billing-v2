from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.timezone import now

from invoices.utils import generate_invoice_pdf  # Reusing your safe LaTeX logic


def email_item_invoice_to_client(invoice):
    """
    Sandbox version of the email utility.
    - Removes .tex attachment for Brevo compatibility.
    - Explicitly refreshes the invoice to catch cloned items.
    """
    try:
        # 1. Sync the relationship so the PDF isn't empty
        invoice.refresh_from_db()
        
        # 2. Generate PDF bytes using your existing xelatex logic
        pdf_bytes = generate_invoice_pdf(invoice)

        profile = invoice.user.profile
        friendly_from = f'"{profile.company_name}" <{settings.DEFAULT_FROM_EMAIL}>'
        reply_address = profile.business_email if profile.business_email else invoice.user.email

        subject = f"Invoice {invoice.number} from {profile.company_name}"
        body = (f"Hi {invoice.client.name},\n\n"
                f"Please find attached invoice {invoice.number}.\n\n"
                f"Regards,\n{profile.company_name}")

        email = EmailMessage(
            subject, 
            body, 
            friendly_from, 
            [invoice.client.email], 
            reply_to=[reply_address]
        )

        # 3. ATTACH ONLY THE PDF (Brevo blocks .tex)
        email.attach(f"Invoice_{invoice.number}.pdf", pdf_bytes, 'application/pdf')

        email.send()
        
        invoice.last_generated = now()
        invoice.status = 'PENDING'
        invoice.save(update_fields=['last_generated', 'status'])
        return True
    except Exception as e:
        print(f"Sandbox Email Error: {e}")
        return False