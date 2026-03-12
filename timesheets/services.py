from django.db import transaction

from core.models import BillingAuditLog
from core.utils import get_anomaly_status
from invoices.models import Invoice

from .models import TimesheetEntry


def create_invoice_from_timesheets(user, client, timesheet_ids):
    """
    Business logic to convert specific timesheets into a single invoice.
    Returns the created Invoice object.
    """
    with transaction.atomic():
        # 1. Fetch and lock the entries
        entries = TimesheetEntry.objects.select_for_update().filter(id__in=timesheet_ids, user=user, is_billed=False)

        if not entries.exists():
            return None

        # 2. Create the Invoice
        invoice = Invoice.objects.create(user=user, client=client, status="DRAFT")

        # 3. Link timesheets directly to invoice (don't create separate InvoiceItems)
        #    This allows proper grouping by category in build_invoice_items_list()
        for entry in entries:
            entry.is_billed = True
            entry.invoice = invoice
            entry.save()

        # 4. Update totals and audit
        Invoice.objects.update_totals(invoice)
        invoice.refresh_from_db()

        # Audit logging using the comprehensive audit function
        try:
            from core.models import AuditHistory
            is_anomaly, comment, audit_context = get_anomaly_status(user, invoice)
            # Prevent duplicate audit logs for same invoice (use get_or_create)
            BillingAuditLog.objects.get_or_create(
                user=user,
                invoice=invoice,
                defaults={
                    "is_anomaly": is_anomaly,
                    "ai_comment": comment,
                    "details": {"total": float(invoice.total_amount), "source": "timesheet_billing"},
                }
            )
            
            # Create audit history record for learning
            AuditHistory.objects.create(
                user=user,
                invoice=invoice,
                checks_run=audit_context.get("checks_run", []),
                flags_raised=[c for c in comment.split(" | ") if c != "OK"],
                comparison_invoices_count=audit_context.get("comparison_invoices_count", 0),
                is_flagged=is_anomaly,
                comparison_mean=audit_context.get("comparison_mean"),
                comparison_stddev=audit_context.get("comparison_stddev"),
                comparison_cv=audit_context.get("comparison_cv"),
            )
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to audit timesheet invoice {invoice.id}: {e}")
            # Still return the invoice even if audit fails

        return invoice
