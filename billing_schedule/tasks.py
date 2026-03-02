# billing_scheduler/tasks.py
import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from items.services import import_recurring_to_invoices

from .models import BillingPolicy

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
        # Check if this user has any policies due today
        due_policies = BillingPolicy.objects.filter(user=user).due_today()

        if not due_policies.exists():
            logger.info(f"No billing policies due today for user {user.username}")
            continue

        logger.info(f"Processing {due_policies.count()} policy/policies for user {user.username}")

        try:
            # Call the service to process all recurring items linked to due policies for this user
            created_invoices = import_recurring_to_invoices(user)

            if created_invoices:
                total_invoices_created += len(created_invoices)
                for policy in due_policies:
                    logger.info(
                        f"Policy '{policy.name}' for user {user.username} fired successfully. "
                        f"Created {len(created_invoices)} invoice(s)."
                    )
                results.append(
                    f"User {user.username}: {len(created_invoices)} invoices created from policies {[p.name for p in due_policies]}"
                )
            else:
                logger.info(f"No items matched policies for user {user.username} - no invoices created")
                results.append(f"User {user.username}: No invoices created (no matching items)")

        except Exception as e:
            logger.error(f"Critical failure processing billing policies for {user.username}: {str(e)}", exc_info=True)
            results.append(f"User {user.username}: ERROR - {str(e)}")

    logger.info(f"Billing queue processing complete. Total invoices created: {total_invoices_created}")
    return results
