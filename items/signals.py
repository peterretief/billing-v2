from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Item
from notifications.models import Notification


@receiver(post_save, sender=Item)
def mark_item_complete(sender, instance, created, **kwargs):
    """
    Mark 'add item' onboarding task as read when an item is created.
    """
    if created:
        Notification.objects.filter(
            user=instance.user,
            message="Step 3: Add your first item.",
            is_read=False
        ).update(is_read=True)
