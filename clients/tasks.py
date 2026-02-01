# tasks.py
from celery import shared_task

from .services import BrevoSenderService


@shared_task
def check_verification():
    BrevoSenderService()
    # ... logic to check status ...