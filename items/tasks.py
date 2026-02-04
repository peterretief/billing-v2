import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from .services import import_recurring_to_invoices

logger = logging.getLogger(__name__)


@shared_task(name="run_automated_billing_cycle") # Use a clean, explicit name
def run_automated_billing_cycle():
    """
    Heartbeat task: Runs once a day to process all 
    recurring items for all active users.
    """
    User = get_user_model()
    # We only run this for active users to save resources
    active_users = User.objects.filter(is_active=True)
    
    total_invoices = 0
    
    for user in active_users:
        try:
            processed = import_recurring_to_invoices(user)
            total_invoices += len(processed)
        except Exception as e:
            logger.error(f"Critical failure in billing cycle for {user.username}: {str(e)}")

    return f"Automated billing complete. Generated {total_invoices} invoices."