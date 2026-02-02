import logging
from datetime import timedelta

from django.db import (
    transaction,
)
from django.utils import timezone

# Models
from core.models import BillingAuditLog
from invoices.models import Invoice

from .models import Item

# Utils
from .utils import email_item_invoice_to_client

logger = logging.getLogger(__name__)

def import_recurring_to_invoices(user):
    today = timezone.now()
    
    # 1. EMERGENCY RESET: Unlink any recurring items currently stuck to DRAFTS
    Item.objects.filter(
        user=user, 
        is_recurring=True, 
        invoice__status='DRAFT'
    ).update(invoice=None)

    # 2. SELECTION: Get master templates not yet billed this month
    templates = Item.objects.filter(
        user=user, 
        is_recurring=True
    ).exclude(
        last_billed_date__month=today.month, 
        last_billed_date__year=today.year
    )

    if not templates.exists():
        logger.info("Nothing to bill today.")
        return []

    new_invoices = []
    client_ids = templates.values_list('client', flat=True).distinct()

    for cid in client_ids:
        if not cid: continue
        
        with transaction.atomic():
            client_templates = templates.filter(client_id=cid)
            client_obj = client_templates.first().client
            
            days_to_due = getattr(client_obj, 'payment_terms', 30) or 30
            calculated_due_date = today.date() + timedelta(days=days_to_due)
            
            invoice = Invoice.objects.create(
                user=user,
                client=client_obj,
                date_issued=today.date(),
                due_date=calculated_due_date,
                status='DRAFT'
            )

            for t in client_templates:
                Item.objects.create(
                    user=user, 
                    client=client_obj, 
                    invoice=invoice,
                    description=t.description, 
                    quantity=t.quantity,
                    unit_price=t.unit_price, 
                    is_recurring=False
                )

            Invoice.objects.update_totals(invoice)
            invoice.refresh_from_db()

            is_huge = float(invoice.total_amount) > 10000
            BillingAuditLog.objects.create(
                user=user, 
                invoice=invoice, 
                is_anomaly=is_huge,
                ai_comment="High value" if is_huge else "",
                details={"total": float(invoice.total_amount)}
            )
            
            if not is_huge:
                new_invoices.append(invoice)

    # 3. THE DISPATCH (Sending the emails)
    # We maintain a list of successfully processed invoices to return to the task
    processed_invoices = []

    for inv in new_invoices:
        try:
            if email_item_invoice_to_client(inv):
                # --- NEW LOGIC START ---
                inv.status = 'PENDING' 
                inv.is_emailed = True      # Stamping for the History Table
                inv.emailed_at = today     # Accurate timestamp for ordering
                inv.save()
                
                # Update the master template's last_billed_date so it leaves Table 1
                templates.filter(client=inv.client).update(last_billed_date=today.date())
                # --- NEW LOGIC END ---
                
                logger.info(f"Successfully sent invoice {inv.id} to {inv.client.name}")
                processed_invoices.append(inv)
            else:
                logger.error(f"Mail delivery failure for invoice {inv.id}")
        except Exception as e:
            logger.error(f"System error during dispatch for invoice {inv.id}: {str(e)}")

    # Returning objects instead of IDs so the Celery task can access attributes
    return processed_invoices