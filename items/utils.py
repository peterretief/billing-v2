import datetime

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.timezone import now

from invoices.utils import generate_invoice_pdf  # Reusing your safe LaTeX logic


def is_first_working_day(date_to_check):
    """
    Checks if the given date is the first Monday-Friday of its month.
    """
    # 1. If it's Saturday (5) or Sunday (6), it's not a working day
    if date_to_check.weekday() > 4:
        return False

    # 2. Check if any day earlier in this same month was a weekday
    # We loop from the 1st of the month up to (but not including) today
    for day in range(1, date_to_check.day):
        test_date = datetime.date(date_to_check.year, date_to_check.month, day)
        if test_date.weekday() <= 4:
            # We found a weekday earlier in the month, so today isn't the first
            return False

    # 3. If we cleared those checks, it is the first working day
    return True


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
        
        # Personalized Greeting
        signature_name = profile.contact_name if profile.contact_name else profile.company_name
        body = (
            f"Hi {invoice.client.name},\n\n"
            f"Please find attached invoice {invoice.number}.\n\n"
            f"Regards,\n{signature_name}"
        )

        email = EmailMessage(subject, body, friendly_from, [invoice.client.email], reply_to=[reply_address])

        # 3. ATTACH ONLY THE PDF (Brevo blocks .tex)
        email.attach(f"Invoice_{invoice.number}.pdf", pdf_bytes, "application/pdf")

        email.send()

        invoice.last_generated = now()
        invoice.status = "PENDING"
        invoice.save(update_fields=["last_generated", "status"])
        return True
    except Exception as e:
        print(f"Sandbox Email Error: {e}")
        return False
