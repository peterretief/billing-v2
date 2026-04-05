# core_project/celery.py
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_project.settings")

app = Celery("core_project")

# Load all Celery settings from Django settings (with CELERY_ prefix)
# This includes CELERY_BEAT_SCHEDULE which is defined in settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks from all apps that have tasks
# Added 'larder' to this list to discover tasks in the larder app.
app.autodiscover_tasks(["invoices", "billing_schedule", "items", "notifications", "clients"])
