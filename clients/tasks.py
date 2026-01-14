# tasks.py
from .services import BrevoSenderService
from celery import shared_task

@shared_task
def check_verification():
    service = BrevoSenderService()
    # ... logic to check status ...