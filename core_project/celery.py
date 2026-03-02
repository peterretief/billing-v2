# core_project/celery.py
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_project.settings")

app = Celery("core_project")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks from billing_schedule and items apps
app.autodiscover_tasks(["billing_schedule", "items"])

app.conf.beat_schedule = {
    "daily-billing-policy-queue": {
        "task": "billing_schedule.tasks.process_daily_billing_queue",
        "schedule": crontab(minute=1, hour=0),  # Runs at 00:01 daily (Africa/Johannesburg)
    },
}
