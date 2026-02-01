import os

from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_project.settings')

app = Celery('core_project')

# Combined Beat Schedule
app.conf.beat_schedule = {
    # Task 1: Check for recurring invoices every weekday at 8:00 AM
    'recurring-invoices-weekday-check': {
        'task': 'invoices.tasks.generate_recurring_monthly_invoices',
        'schedule': crontab(minute=0, hour=8, day_of_week='mon,tue,wed,thu,fri'),
    },
    # Task 2: Mid-month report on the 15th
    'send-mid-month-financial-assessment': {
        'task': 'invoices.tasks.send_mid_month_financial_report',
        'schedule': crontab(day_of_month=15, hour=9, minute=0),
    },
}

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()