import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_project.settings')

app = Celery('core_project')

app.conf.beat_schedule = {
    # NEW: Your smarter, policy-aware billing engine
    'daily-automated-billing-cycle': {
        'task': 'tasks.run_automated_billing_cycle', 
        'schedule': crontab(minute=1, hour=0), # Runs at 12:01 AM every day
    },
    # Keep your mid-month report if you still use it
    'send-mid-month-financial-assessment': {
        'task': 'invoices.tasks.send_mid_month_financial_report',
        'schedule': crontab(day_of_month=15, hour=9, minute=0),
    },
}

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()