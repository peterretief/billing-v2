import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from billing_schedule.models import BillingPolicy  # Import the new policy model

# Models
from core.models import BillingAuditLog
from invoices.models import Invoice

from .models import Item

# Utils
from .utils import email_item_invoice_to_client

logger = logging.getLogger(__name__)

def import_recurring_to_invoices(user):
    today = timezone.now()
    # ... your logic ...
    items_to_bill = Item.objects.filter(user=user, is_recurring=True)
    print(f"DEBUG: Found {items_to_bill.count()} recurring items for {user.username}")


    # --- STEP 1: IDENTIFY DUE POLICIES ---
    # We use the 'due_today' manager we built to find which schedules trigger today
    due_policies = BillingPolicy.objects.filter(user=user).due_today()
    
    if not due_policies.exists():
        logger.info(f"No billing policies are scheduled to run today for user {user.username}.")
        return []

    # --- STEP 2: EMERGENCY RESET ---
    # Unlink any recurring items currently stuck to DRAFTS
    Item.objects.filter(
        user=user, 
        is_recurring=True, 
        invoice__status='DRAFT'
    ).update(invoice=None)

    # --- STEP 3: SELECTION (The Bridge) ---
    # Filter templates that are:
    # 1. Recurring
    # 2. Linked to a policy that is due TODAY
    # 3. Haven't been billed yet today
    templates = Item.objects.filter(
        user=user, 
        is_recurring=True,
        billing_policy__in=due_policies
    ).exclude(
        last_billed_date=today.date()
    )

    if not templates.exists():
        logger.info("No items match the current scheduled policies for today.")
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
            
            # Generate the Invoice
            invoice = Invoice.objects.create(
                user=user,
                client=client_obj,
                date_issued=today.date(),
                due_date=calculated_due_date,
                status='DRAFT'
            )

            # Create specific line items for this specific invoice
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

            # Audit logging
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

    # --- STEP 4: THE DISPATCH ---
    processed_invoices = []

    for inv in new_invoices:
        try:
            if email_item_invoice_to_client(inv):
                inv.status = 'PENDING' 
                inv.is_emailed = True      
                inv.emailed_at = today     
                inv.save()
                
                # IMPORTANT: Update the master template's date so it doesn't fire again today
                # We filter by client and policy to be precise
                templates.filter(client=inv.client).update(last_billed_date=today.date())
                
                logger.info(f"Successfully sent invoice {inv.id} to {inv.client.name}")
                processed_invoices.append(inv)
            else:
                logger.error(f"Mail delivery failure for invoice {inv.id}")
        except Exception as e:
            logger.error(f"System error during dispatch for invoice {inv.id}: {str(e)}")

    return processed_invoices