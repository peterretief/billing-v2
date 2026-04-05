import logging
from celery import shared_task
from django.contrib.auth import get_user_model

from items.services import import_recurring_to_invoices

logger = logging.getLogger(__name__)


@shared_task(name="billing_schedule.tasks.process_daily_billing_queue")
def process_daily_billing_queue():
    User = get_user_model()

    for user in User.objects.filter(is_active=True):
        try:
            invoices = import_recurring_to_invoices(user)
            logger.info(f"{user.username}: {len(invoices)} invoice(s) created and sent.")
        except Exception as e:
            logger.error(f"{user.username}: billing failed — {e}", exc_info=True)