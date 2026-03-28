# Signal to create default categories for new users
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import DefaultWorkCategory, WorkCategory

User = get_user_model()


@receiver(post_save, sender=User)
def create_default_work_categories(sender, instance, created, **kwargs):
    if created:
        # 1. Create the actual category for this specific user
        category, _ = WorkCategory.objects.get_or_create(
            user=instance, 
            name="General Work",
            defaults={"description": "System default category"}
        )
        
        # 2. Designate it as the 'Default' link for this user
        DefaultWorkCategory.objects.get_or_create(
            user=instance,
            defaults={"work_category": category}
        )
