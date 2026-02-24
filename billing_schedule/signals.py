from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import BillingPolicy


# billing_schedule/signals.py
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_billing_policy(sender, instance, created, **kwargs):
    if created:
        BillingPolicy.objects.get_or_create(
            user=instance,
            run_day=1,  # The unique constraint field
            defaults={"name": "Default Monthly Schedule", "is_active": True, "special_rule": "NONE"},
        )
