
from django.conf import settings


from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
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


@receiver(post_delete, sender=ItemInventoryLink)
def restore_stock_on_link_deletion(sender, instance, **kwargs):
    """
    If a link is deleted, return the stock to inventory.
    In the real-time model, stock is decremented immediately when the link is created.
    """
    if not instance.auto_decrement:
        return

    # Check if inventory integration is enabled for this user
    settings = IntegrationSettings.objects.filter(user=instance.user).first()
    if not settings or not settings.inventory_enabled:
        return

    item = instance.item
    inv_item = instance.inventory_item
    return_amount = item.quantity * instance.quantity_multiplier
    
    inv_item.current_stock += return_amount
    inv_item.save(update_fields=['current_stock'])
    
    StockTransaction.objects.create(
        user=inv_item.user,
        inventory_item=inv_item,
        transaction_type='IN',
        quantity=return_amount,
        reference=f"Stock restored: Link to Item '{item.id}' deleted",
        notes=f"Unbilled item or billed item removed"
    )
