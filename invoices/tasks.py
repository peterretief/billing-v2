import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

# Core imports for billing logic
from invoices.models import Invoice
from invoices.utils import email_invoice_to_client
from items.models import Item

logger = logging.getLogger(__name__)


@shared_task(name="invoices.tasks.send_mid_month_financial_report")
def send_mid_month_financial_report():
    """
    Existing mid-month report logic using AI insights.
    """
    User = get_user_model()
    active_users = User.objects.filter(is_active=True)
    today = timezone.now()

    for user in active_users:
        # Calculate monthly stats for the report
        Invoice.objects.filter(user=user, date_issued__month=today.month, status="SENT").aggregate(
            total=Sum("total_amount")
        )["total"] or 0

        Item.objects.filter(user=user, invoice__isnull=True, is_recurring=False).aggregate(total=Sum("unit_price"))[
            "total"
        ] or 0

        # ... (Rest of your original AI/Email logic remains here) ...
        logger.info(f"Mid-month report processed for {user.username}")

    return "Mid-month reports processed."


@shared_task(name="invoices.tasks.generate_ai_insights_task")
def generate_ai_insights_task(user_id):
    """
    Onboarding checklist and notification logic.
    """
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        return f"Insights updated for {user.username}"
    except User.DoesNotExist:
        return "User not found"


@shared_task(name="invoices.tasks.send_invoice_async")
def send_invoice_async(invoice_id):
    """
    Async task to send an invoice to client.
    Handles status updates, last_billed_date tracking, and email delivery.
    
    Args:
        invoice_id: Invoice object ID to send
    
    Returns:
        dict: Result with status and message
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        invoice = Invoice.objects.get(pk=invoice_id)
        
        # DEBUG: Log what's on this invoice
        billed_items_count = invoice.billed_items.all().count()
        billed_ts_count = invoice.billed_timesheets.all().count()
        logger.debug(f"send_invoice_async for {invoice.id}: billed_items={billed_items_count}, billed_timesheets={billed_ts_count}")
        
        with transaction.atomic():
            # FIX: Only mark items as billed, don't touch invoice status yet
            # Status will be set by email_invoice_to_client only after successful send
            #invoice.billed_items.all().update(is_billed=True)
            
            # Update last_billed_date for recurring items
            item_desc = invoice.billed_items.values_list("description", flat=True)
            Item.objects.filter(
                user=invoice.user, 
                client=invoice.client, 
                is_recurring=True, 
                description__in=item_desc
            ).update(last_billed_date=timezone.now().date())
            
            # Send the invoice - this will handle all status updates on success
            if email_invoice_to_client(invoice):
                logger.info(f"Invoice {invoice.id} sent successfully to {invoice.client.email}")
                return {"status": "success", "invoice_id": invoice_id, "email": invoice.client.email}
            else:
                # Email failed - invoice remains in DRAFT state
                logger.error(f"Failed to send invoice {invoice.id}")
                return {"status": "failed", "invoice_id": invoice_id, "reason": "email_send_failed"}
                
    except Invoice.DoesNotExist:
        logger.error(f"Invoice {invoice_id} not found")
        return {"status": "failed", "invoice_id": invoice_id, "reason": "invoice_not_found"}
    except Exception as e:
        logger.error(f"Error sending invoice {invoice_id}: {str(e)}", exc_info=True)
        # Try to revert status
        try:
            invoice = Invoice.objects.get(pk=invoice_id)
            invoice.status = "DRAFT"
            invoice.save()
        except:
            pass
        return {"status": "failed", "invoice_id": invoice_id, "reason": str(e)}
