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
    Email utility with proper Brevo delivery tracking.
    - Captures Anymail message ID for delivery tracking
    - Creates InvoiceEmailStatusLog for audit trail
    - Logs failures with full error context
    """
    import logging
    from invoices.models import InvoiceEmailStatusLog
    
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Sync the relationship so the PDF isn't empty
        invoice.refresh_from_db()

        # 2. Generate PDF bytes 
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
            f"Total Due: {profile.currency} {invoice.total_amount:,.2f}\n"
            f"Due Date: {invoice.due_date}\n\n"
            f"Regards,\n{signature_name}"
        )

        email = EmailMessage(subject, body, friendly_from, [invoice.client.email], reply_to=[reply_address])

        # Attach PDF
        email.attach(f"Invoice_{invoice.number}.pdf", pdf_bytes, "application/pdf")

        # Send via Brevo backend to get Anymail tracking
        try:
            sent_messages = email.send()
            logger.info(f"Email sent for recurring invoice {invoice.id}: {sent_messages} messages")
        except Exception as e:
            logger.error(f"Failed to send email for recurring invoice {invoice.id}: {e}")
            raise

        # Capture Anymail delivery tracking
        anymail_status = getattr(email, "anymail_status", None)
        message_id = anymail_status.message_id if anymail_status else None

        if not message_id:
            logger.error(
                f"WARNING: No message_id captured from Anymail for recurring invoice {invoice.id}! "
                f"Delivery tracking will not be available."
            )
            # Don't mark as sent if we can't track it
            raise Exception("Failed to capture message ID from email service - delivery cannot be tracked")

        # Create the tracking record
        log = InvoiceEmailStatusLog.objects.create(
            user=invoice.user, 
            invoice=invoice, 
            brevo_message_id=message_id, 
            status="sent"
        )
        logger.info(f"Created delivery log {log.id} with message_id={log.brevo_message_id}")

        # Update invoice status
        invoice.last_generated = now()
        invoice.status = "PENDING"
        invoice.is_emailed = True
        invoice.emailed_at = now()
        invoice.save(update_fields=["last_generated", "status", "is_emailed", "emailed_at"])
        return True
        
    except Exception as e:
        logger.error(f"Failed to email recurring invoice {invoice.id}: {e}", exc_info=True)
        invoice.last_email_error = str(e)
        invoice.save(update_fields=["last_email_error"])
        return False
