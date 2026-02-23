from django.db import transaction

from invoices.models import Invoice, InvoiceItem
from core.models import BillingAuditLog
from core.utils import get_anomaly_status

from .models import TimesheetEntry


def create_invoice_from_timesheets(user, client, timesheet_ids):
    """
    Business logic to convert specific timesheets into a single invoice.
    Returns the created Invoice object.
    """
    with transaction.atomic():
        # 1. Fetch and lock the entries
        entries = TimesheetEntry.objects.select_for_update().filter(
            id__in=timesheet_ids,
            user=user,
            is_billed=False
        )

        if not entries.exists():
            return None

        # 2. Create the Invoice
        invoice = Invoice.objects.create(
            user=user,
            client=client,
            status='DRAFT'
        )

        # 3. Create Line Items
        for entry in entries:
            InvoiceItem.objects.create(
                invoice=invoice,
                description=f"{entry.date}: {entry.description}",
                quantity=entry.hours,
                unit_price=entry.hourly_rate
            )
            # Link and Mark as billed
            entry.is_billed = True
            entry.invoice = invoice
            entry.save()
        
        # 4. Update totals and audit
        Invoice.objects.update_totals(invoice)
        invoice.refresh_from_db()
        
        # Audit logging using the comprehensive audit function
        try:
            is_anomaly, comment = get_anomaly_status(user, invoice)
            BillingAuditLog.objects.create(
                user=user,
                invoice=invoice,
                is_anomaly=is_anomaly,
                ai_comment=comment,
                details={
                    "total": float(invoice.total_amount),
                    "source": "timesheet_billing"
                }
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to audit timesheet invoice {invoice.id}: {e}")
            # Still return the invoice even if audit fails
            
        return invoice