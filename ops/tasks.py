from celery import shared_task
from django.utils import timezone

from items.utils import is_first_working_day

from .services import populate_batch, process_pending_queue


@shared_task
def daily_billing_manager_task():
    today = timezone.now().date()

    # 1. Check if it's the First Working Day
    if is_first_working_day(today):
        # 2. Populate the BillingBatch for all active users
        count = populate_batch()

        # 3. Trigger the processing (can be a separate task call)
        process_pending_queue.delay()

        return f"Successfully queued {count} users for the first working day."

    return "Not the first working day. No queue created."
