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
    
    # --- STEP 1: EMERGENCY RESET ---
    # Unlink any recurring items currently stuck to DRAFTS
    Item.objects.filter(user=user, is_recurring=True, invoice__status="DRAFT").update(invoice=None)

    # --- STEP 2: Define month range for duplicate prevention ---
    current_month_start = today.date().replace(day=1)
    if today.month == 12:
        current_month_end = today.date().replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        current_month_end = today.date().replace(month=today.month + 1, day=1) - timedelta(days=1)

    # --- STEP 3: IDENTIFY TEMPLATES TO BILL ---
    # Include items from TWO sources:
    # A) Items linked to billing policies that are due TODAY
    # B) Items in the Master Recurring Queue (is_recurring=True, invoice=NULL)
    
    due_policies = BillingPolicy.objects.filter(user=user).due_today()
    
    # Items linked to due policies
    policy_items = Item.objects.filter(
        user=user, 
        is_recurring=True, 
        billing_policy__in=due_policies
    ).exclude(last_billed_date__range=[current_month_start, current_month_end])
    
    # Items in the Master Recurring Queue (queued for invoicing, not yet billed)
    queued_items = Item.objects.filter(
        user=user,
        is_recurring=True,
        invoice__isnull=True,  # Not linked to any invoice yet
    ).exclude(
        last_billed_date__range=[current_month_start, current_month_end]
    )
    
    # Combine both sources, removing duplicates
    template_ids = set(policy_items.values_list('id', flat=True)) | set(queued_items.values_list('id', flat=True))
    
    if not template_ids:
        if due_policies.exists():
            logger.info(f"No queued items found for user {user.username} from due policies.")
        else:
            logger.info(f"No billing policies due today and no queued items for user {user.username}.")
        return []
    
    templates = Item.objects.filter(id__in=template_ids)

    new_invoices = []
    client_ids = templates.values_list("client", flat=True).distinct()

    for cid in client_ids:
        if not cid:
            continue

        with transaction.atomic():
            client_templates = templates.filter(client_id=cid)
            client_obj = client_templates.first().client

            days_to_due = getattr(client_obj, "payment_terms", 30) or 30
            calculated_due_date = today.date() + timedelta(days=days_to_due)

            # Generate the Invoice
            invoice = Invoice.objects.create(
                user=user, client=client_obj, date_issued=today.date(), due_date=calculated_due_date, status="DRAFT"
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
                    is_recurring=False,
                )

            Invoice.objects.update_totals(invoice)
            invoice.refresh_from_db()

            # Audit logging using the new comprehensive audit function
            try:
                from core.utils import get_anomaly_status
                from core.models import AuditHistory

                is_anomaly, comment, audit_context = get_anomaly_status(user, invoice)
                BillingAuditLog.objects.create(
                    user=user,
                    invoice=invoice,
                    is_anomaly=is_anomaly,
                    ai_comment=comment,
                    details={"total": float(invoice.total_amount), "source": "items_billing"},
                )
                
                # Create audit history record for learning
                AuditHistory.objects.create(
                    user=user,
                    invoice=invoice,
                    checks_run=audit_context.get("checks_run", []),
                    flags_raised=[c for c in comment.split(" | ") if c.startswith("❌") or c.startswith("⚠️")],
                    comparison_invoices_count=audit_context.get("comparison_invoices_count", 0),
                    is_flagged=is_anomaly,
                    comparison_mean=audit_context.get("comparison_mean"),
                    comparison_stddev=audit_context.get("comparison_stddev"),
                    comparison_cv=audit_context.get("comparison_cv"),
                )

                # NEVER BLOCK - always add to processing regardless of audit flags
                # Flagged invoices will appear in dashboard for manual review
                new_invoices.append(invoice)
            except Exception as e:
                logger.error(f"Failed to audit invoice {invoice.id}: {e}")
                # Still add to new_invoices even if audit fails
                new_invoices.append(invoice)

    # --- STEP 4: THE DISPATCH ---
    processed_invoices = []

    for inv in new_invoices:
        try:
            if email_item_invoice_to_client(inv):
                inv.status = "PENDING"
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
