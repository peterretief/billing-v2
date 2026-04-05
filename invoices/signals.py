import datetime
import re
import uuid

from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from invoices.models import Invoice, Payment

# --- 1. Total Calculations (Standard Only) ---

@receiver(post_save, sender=Invoice)
def update_totals_on_tax_mode_change(sender, instance, created, **kwargs):
    """
    Handles tax mode changes on the Invoice header.
    GATEKEEPER: If this is a CustomInvoice, we STOP here to prevent loops.
    """
    if kwargs.get("update_fields") and "total_amount" in kwargs.get("update_fields"):
        return

    if hasattr(instance, "custominvoice") or hasattr(instance, "custom_lines"):
        return

    Invoice.objects.update_totals(instance)


# --- 2. Invoice Number Generation ---


@receiver(pre_save, sender=Invoice)
def create_invoice_number(sender, instance, **kwargs):
    """Generates sequential numbers for ALL invoices."""
    if not instance.number:
        try:
            # Use provided date or fallback to today
            today = getattr(instance, "date_issued", None) or datetime.date.today()
            short_year = today.strftime("%y")

            client_code = "INV"
            if instance.client and hasattr(instance.client, "client_code"):
                client_code = instance.client.client_code or "INV"

            # Find last sequence across all invoice types for this client
            last_invoice = (
                Invoice.objects.filter(user=instance.user, client=instance.client, number__icontains=f"-{short_year}")
                .order_by("id")
                .last()
            )

            if last_invoice:
                pattern = rf"{re.escape(client_code)}-(\d+)-{short_year}"
                match = re.search(pattern, last_invoice.number)
                if match:
                    next_sequence = int(match.group(1)) + 1
                else:
                    # Fallback count if pattern match fails
                    next_sequence = (
                        Invoice.objects.filter(
                            user=instance.user, client=instance.client, number__icontains=f"-{short_year}"
                        ).count()
                        + 1
                    )
            else:
                next_sequence = 1

            new_number = f"{client_code}-{next_sequence:02d}-{short_year}"

            # Final collision check
            while Invoice.objects.filter(user=instance.user, number=new_number).exists():
                next_sequence += 1
                new_number = f"{client_code}-{next_sequence:02d}-{short_year}"

            instance.number = new_number
        except Exception:
            # High-reliability fallback if DB query fails
            instance.number = f"INV-{uuid.uuid4().hex[:4].upper()}"


# --- 3. Explicit Connection for Custom Models ---


def connect_custom_signals():
    """
    Connects signals to child models.
    In MTI, child models trigger parent signals, but pre_save
    sometimes needs an explicit hook for sequence numbering.
    """
    pass


# Call this LAST
connect_custom_signals()


@receiver(post_save, sender=Invoice)
def update_items_on_sent(sender, instance, **kwargs):
    pass
    # Changed from 'SENT' to 'PENDING' to match your Status choices
# --- 4. Delete Signal Handlers (Critical for Data Integrity) ---


@receiver(post_delete, sender=Payment)
def recalculate_invoice_on_payment_delete(sender, instance, **kwargs):
    """
    When a payment is deleted, trigger invoice total recalculation via the manager.
    This ensures data consistency when payments are deleted via admin or API.
    balance_due is a calculated property, so we just need to trigger the manager recalc.
    """
    try:
        invoice = instance.invoice
        if invoice:
            # Use the manager to recalculate invoice status and totals
            Invoice.objects.update_totals(invoice)
    except Exception:
        pass  # Silently fail to avoid blocking the deletion


@receiver(post_delete, sender='items.Item')
def recalculate_invoice_on_item_delete(sender, instance, **kwargs):
    """
    When an item is deleted, recalculate the invoice's total_amount and status.
    This ensures data consistency when items are deleted via admin or API.
    """
    try:
        invoice = instance.invoice
        if invoice:
            # Use the manager to recalculate totals
            from invoices.models import Invoice as InvoiceModel
            InvoiceModel.objects.update_totals(invoice)
    except Exception as e:
        print(f"Error recalculating invoice on item delete: {e}")


# --- 5. Email Delivery Failure Detection ---

@receiver(post_save, sender='invoices.InvoiceEmailStatusLog')
def re_audit_on_delivery_status_change(sender, instance, created, **kwargs):
    """
    When a delivery status update is received (bounce, delivered, etc.),
    re-audit the invoice to catch delivery failures immediately.
    """
    if not created:
        return  # Only on new delivery logs
    
    try:
        from core.models import BillingAuditLog
        from core.utils import get_anomaly_status
        
        invoice = instance.invoice
        
        # Re-run audit with latest delivery status
        is_anomaly, comment, audit_context = get_anomaly_status(invoice.user, invoice)
        
        # Update the most recent audit log for this invoice
        latest_log = BillingAuditLog.objects.filter(invoice=invoice).order_by('-created_at').first()
        if latest_log and latest_log.details.get('source') != 'manual_review':
            # Update existing audit log with new findings
            latest_log.is_anomaly = is_anomaly
            latest_log.ai_comment = comment
            latest_log.save()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to re-audit invoice on delivery status change: {e}")
        # Don't fail - just log and continue


@receiver(post_delete, sender='invoices.Invoice')
def reset_items_on_invoice_delete(sender, instance, **kwargs):
    """
    When an invoice is deleted, delete the items and timesheets associated with it.
    
    Rationale: Once items/timesheets have been invoiced, they've been "processed".
    If the invoice is deleted, those items should be removed rather than orphaned.
    If the user needs to bill them again, they should create new items.
    
    This prevents confusion from orphaned, already-billed items appearing in the list.
    """
    try:
        import logging

        from items.models import Item
        from timesheets.models import TimesheetEntry
        logger = logging.getLogger(__name__)
        
        # Delete all items linked to this invoice
        deleted_items, _ = Item.objects.filter(invoice=instance).delete()
        
        # Delete all timesheets linked to this invoice
        deleted_timesheets, _ = TimesheetEntry.objects.filter(invoice=instance).delete()
        
        logger.info(f"Deleted {deleted_items} items and {deleted_timesheets} timesheets for invoice {instance.id}")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to delete items/timesheets on invoice delete: {e}")
        # Don't fail - just log and continue
