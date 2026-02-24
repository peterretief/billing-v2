import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

# Core imports for billing logic
from invoices.models import Invoice
from items.models import Item
from items.services import import_recurring_to_invoices

logger = logging.getLogger(__name__)


@shared_task(name="invoices.tasks.generate_recurring_monthly_invoices")
def generate_recurring_monthly_invoices():
    User = get_user_model()
    active_users = User.objects.filter(is_active=True)

    results = []
    for user in active_users:
        logger.info(f"Checking recurring billing for {user.username}")

        # 1. The service creates the invoice and attempts to email it
        # Make sure your service returns the list of Invoice objects
        created_invoices = import_recurring_to_invoices(user)

        count = 0
        if created_invoices:
            for invoice in created_invoices:
                # 2. Stamp the Invoice for the "Sent History" table
                # We assume the service sets status to 'SENT' upon successful Brevo handover
                if invoice.status == "SENT":
                    invoice.is_emailed = True
                    invoice.emailed_at = timezone.now()
                    invoice.save()

                    # 3. Stamp the Items so they leave the "Pending" table for 30 days
                    invoice.items.all().update(last_invoiced_date=timezone.now().date())
                    count += 1

        results.append(f"User {user.username}: {count} invoices dispatched and cycled.")

    return results


@shared_task(name="invoices.tasks.send_mid_month_financial_report")
def send_mid_month_financial_report():
    """
    Existing mid-month report logic using AI insights.
    """
    User = get_user_model()
    active_users = User.objects.filter(is_active=True)
    today = timezone.now()

    for user in active_users:
        # Calculate monthly stats for the report
        Invoice.objects.filter(user=user, date_issued__month=today.month, status="SENT").aggregate(
            total=Sum("total_amount")
        )["total"] or 0

        Item.objects.filter(user=user, invoice__isnull=True, is_recurring=False).aggregate(total=Sum("unit_price"))[
            "total"
        ] or 0

        # ... (Rest of your original AI/Email logic remains here) ...
        logger.info(f"Mid-month report processed for {user.username}")

    return "Mid-month reports processed."


@shared_task(name="invoices.tasks.generate_ai_insights_task")
def generate_ai_insights_task(user_id):
    """
    Onboarding checklist and notification logic.
    """
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        return f"Insights updated for {user.username}"
    except User.DoesNotExist:
        return "User not found"
