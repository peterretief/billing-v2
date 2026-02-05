import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

# Import your verified billing logic and the new models
from items.services import import_recurring_to_invoices
from items.utils import is_first_working_day  # We'll build this utility next

from .models import BillingBatch

logger = logging.getLogger(__name__)
User = get_user_model()

def populate_monthly_batch():
    """
    Identifies all active users and creates a queue entry for today.
    Typically called by a Celery task on the First Working Day.
    """
    today = timezone.now().date()
    
    # Optional: Safety check to ensure we only run on the first working day
    if not is_first_working_day(today):
        logger.info(f"Skipping batch population: {today} is not the first working day.")
        return 0

    active_users = User.objects.filter(is_active=True)
    queued_count = 0

    for user in active_users:
        # get_or_create prevents duplicate queue items if the task re-runs
        batch_item, created = BillingBatch.objects.get_or_create(
            user=user,
            scheduled_date=today
        )
        if created:
            queued_count += 1
            
    logger.info(f"Created {queued_count} billing queue items for {today}")
    return queued_count


def process_ops_queue(limit=50):
    """
    The 'Worker' service. Picks up unprocessed items from the BillingBatch 
    and executes the actual invoicing logic.
    """
    # Grab a batch of unprocessed items
    pending_items = BillingBatch.objects.filter(
        is_processed=False,
        scheduled_date=timezone.now().date()
    ).select_related('user', 'user__userprofile')[:limit]

    processed_count = 0

    for item in pending_items:
        try:
            with transaction.atomic():
                # 1. Trigger the heavy lifting logic we already tested
                # This creates invoices, emails them, and returns the list
                results = import_recurring_to_invoices(item.user)
                
                # 2. Mark this user as finished in the Ops Queue
                item.is_processed = True
                item.processed_at = timezone.now()
                item.metadata = {
                    'invoices_created': len(results),
                    'currency_used': getattr(item.user.userprofile, 'currency', 'USD')
                }
                item.save()
                processed_count += 1
                
                logger.info(f"Ops Queue: Successfully processed billing for {item.user.username}")

        except Exception as e:
            item.error_message = str(e)
            item.save()
            logger.error(f"Ops Queue Error for {item.user.username}: {str(e)}")

    return processed_count