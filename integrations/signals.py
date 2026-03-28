
from django.conf import settings


from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.apps import apps
from inventory.models import StockTransaction
from integrations.models import ItemInventoryLink, IntegrationSettings

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_integration_settings(sender, instance, created, **kwargs):
    if created:
        # This only runs when a NEW user is saved
        IntegrationSettings.objects.get_or_create(
            user=instance, 
            defaults={'inventory_enabled': True} # Set your default plugin state here
        )


@receiver(pre_save, sender="invoices.Invoice")
def track_invoice_status(sender, instance, **kwargs):
    """Store the old status so we know if it transitions to Sent/Paid."""
    if instance.pk:
        Invoice = apps.get_model('invoices', 'Invoice')
        try:
            old_invoice = Invoice.objects.get(pk=instance.pk)
            instance._old_status = old_invoice.status
        except Invoice.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save, sender="invoices.Invoice")
def handle_inventory_on_invoice_transition(sender, instance, created, **kwargs):
    """
    Auto-decrement stock when invoice moves out of DRAFT.
    Auto-increment stock when invoice moves to CANCELLED.
    """
    old_status = getattr(instance, '_old_status', None)
    
    # Needs to transition from DRAFT -> PENDING or PAID
    if old_status == "DRAFT" and instance.status in ["PENDING", "PAID"]:
        _modify_stock(instance, transaction_type='OUT')
        
    # Or transition from PENDING/PAID -> CANCELLED (Return stock)
    elif old_status in ["PENDING", "PAID"] and instance.status == "CANCELLED":
        _modify_stock(instance, transaction_type='IN')

def _modify_stock(invoice, transaction_type):
    settings = IntegrationSettings.objects.filter(user=invoice.user).first()
    if not settings or not settings.inventory_enabled:
        return

    for billed_item in invoice.billed_items.all():
        links = ItemInventoryLink.objects.filter(item=billed_item, auto_decrement=True)
        for link in links:
            modifier_amount = billed_item.quantity * link.quantity_multiplier
            inv_item = link.inventory_item
            
            if transaction_type == 'OUT':
                ref_msg = f"Auto-deduction for Invoice {invoice.number}"
                inv_item.current_stock -= modifier_amount
            elif transaction_type == 'IN':
                ref_msg = f"Stock returned from Cancelled Invoice {invoice.number}"
                inv_item.current_stock += modifier_amount
            
            StockTransaction.objects.create(
                user=inv_item.user,
                inventory_item=inv_item,
                transaction_type=transaction_type,
                quantity=modifier_amount,
                reference=ref_msg,
                notes=f"Linked to billing item: {billed_item.name}"
            )
            inv_item.save(update_fields=['current_stock'])
