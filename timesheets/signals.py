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
		for default in DefaultWorkCategory.objects.all():
			WorkCategory.objects.get_or_create(user=instance, name=default.name, defaults={"metadata_schema": default.metadata_schema})
