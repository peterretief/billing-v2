from django.db.models.signals import post_save
from django.dispatch import receiver

from notifications.models import Notification

from .models import Client


@receiver(post_save, sender=Client)
def mark_client_onboarding_complete(sender, instance, created, **kwargs):
    if created:
        # Find the specific onboarding notification for this user
        # We look for the message string we used in services.py
        Notification.objects.filter(
            user=instance.user, 
            message__icontains="Step 2: Create your first client",
            is_read=False
        ).update(is_read=True)