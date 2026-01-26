from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in

from .models import UserProfile
from notifications.models import Notification
from notifications.tasks import generate_notifications_async
from timesheets.models import TimesheetEntry

# --- 1. Generation Logic ---

@receiver(user_logged_in)
def user_logged_in_receiver(sender, request, user, **kwargs):
    """
    Triggers when a user logs in. 
    Ensure generate_notifications uses get_or_create internally 
    to prevent the "wall of buttons" you saw.
    """
    generate_notifications_async.delay(user.id)


# --- 2. Completion Logic (Step 1: Profile) ---

@receiver(post_save, sender=UserProfile)
def mark_profile_complete(sender, instance, **kwargs):
    """
    Step 1: Mark profile task as read when business details are saved.
    """
    if instance.company_name and instance.address:
        # Use .filter().update() instead of get_or_create().update()
        # This targets ALL matching profile notifications and marks them read.
        Notification.objects.filter(
            user=instance.user,
            message__icontains="profile",
            is_read=False
        ).update(is_read=True)


# --- 3. Completion Logic (Step 2: Client) ---

@receiver(post_save, sender=UserProfile)
def mark_client_complete(sender, instance, **kwargs):
    """
    Step 2: Mark client task as read when a client is created.
    Note: This is handled in clients/signals.py
    """
    pass


# --- 4. Completion Logic (Step 4: Timesheets) ---

@receiver(post_save, sender=TimesheetEntry)
def mark_timesheet_complete(sender, instance, created, **kwargs):
    """
    Step 4: Mark timesheet task as read on the first successful log.
    """
    if created:
        Notification.objects.filter(
            user=instance.user,
            message__icontains="Step 4",
            is_read=False
        ).update(is_read=True)