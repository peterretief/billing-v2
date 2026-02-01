import logging
from datetime import timedelta

from django.db import transaction
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
            # Fetch the client to get their specific payment terms
            client_obj = client_templates.first().client
            
            # Use client's specific terms (default to 30 if field is empty/null)
            days_to_due = getattr(client_obj, 'payment_terms', 30) or 30
            calculated_due_date = today.date() + timedelta(days=days_to_due)
            
            # Create Invoice
            invoice = Invoice.objects.create(
                user=user,
                client=client_obj,
                date_issued=today.date(),
                due_date=calculated_due_date, # DYNAMICALLY CALCULATED
                status='DRAFT'
            )

            # Clone Items from master templates
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

            # Calculate Subtotals and Totals
            Invoice.objects.update_totals(invoice)
            invoice.refresh_from_db()

            # Audit & Anomaly Detection
            is_huge = float(invoice.total_amount) > 10000
            BillingAuditLog.objects.create(
                user=user, 
                invoice=invoice, 
                is_anomaly=is_huge,
                ai_comment="High value" if is_huge else "",
                details={"total": float(invoice.total_amount)}
            )
            
            # If AI flags it as an anomaly, we don't add to the auto-send list
            if not is_huge:
                new_invoices.append(invoice)

    # 3. THE DISPATCH (Sending the emails)
    for inv in new_invoices:
        try:
            if email_item_invoice_to_client(inv):
                inv.status = 'PENDING' # Mark as 'Sent'
                inv.save()
                
                # Update the master template's last_billed_date
                templates.filter(client=inv.client).update(last_billed_date=today.date())
                logger.info(f"Successfully sent invoice {inv.id} to {inv.client.name}")
            else:
                logger.error(f"Mail delivery failure for invoice {inv.id}")
        except Exception as e:
            logger.error(f"System error during dispatch for invoice {inv.id}: {str(e)}")

    return [i.id for i in new_invoices]