# billing_scheduler/tasks.py
import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from items.services import import_recurring_to_invoices

logger = logging.getLogger(__name__)


@shared_task(name="billing_schedule.tasks.process_daily_billing_queue")
def process_daily_billing_queue():
    """
    Daily Celery Beat task that processes all due billing policies for all active users.
    
    - Checks which billing policies are due today for each user
    - Calls import_recurring_to_invoices to process items linked to those policies
    - Logs results for audit trail
    """
    User = get_user_model()
    active_users = User.objects.filter(is_active=True)

    results = []
    total_invoices_created = 0

    for user in active_users:
        try:
            # Call the service to process all recurring items
            # This includes BOTH items from due policies AND items in the Master Recurring Queue
            created_invoices = import_recurring_to_invoices(user)

            if created_invoices:
                total_invoices_created += len(created_invoices)
                logger.info(
                    f"User {user.username}: {len(created_invoices)} invoice(s) created and sent."
                )
                results.append(
                    f"User {user.username}: {len(created_invoices)} invoices created and sent"
                )
            else:
                logger.info(f"User {user.username}: No invoices created (no queued items or policies due)")
                results.append(f"User {user.username}: No invoices created")

        except Exception as e:
            logger.error(f"Critical failure processing billing policies for {user.username}: {str(e)}", exc_info=True)
            results.append(f"User {user.username}: ERROR - {str(e)}")

    logger.info(f"Billing queue processing complete. Total invoices created: {total_invoices_created}")
    return results
