# core_project/celery.py
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_project.settings")

app = Celery("core_project")
app.config_from_object("django.conf:settings", namespace="CELERY")

# ADD THIS LINE to force discovery of the items tasks
app.autodiscover_tasks(["items"])

app.conf.beat_schedule = {
    "daily-automated-billing-cycle": {
        "task": "run_automated_billing_cycle",  # Use the explicit name here
        "schedule": crontab(minute=1, hour=0),
    },
}
