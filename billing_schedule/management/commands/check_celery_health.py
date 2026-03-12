"""
Health check for Celery scheduled tasks.
Verifies that daily billing queue task actually executed.
Run as cron job: 0 8 * * * python manage.py check_celery_health
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import BillingAuditLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Verify Celery scheduled tasks are executing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=25,
            help="How many hours back to check (default: 25)",
        )
        parser.add_argument(
            "--alert",
            action="store_true",
            help="Send alert on failure (requires monitoring integration)",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        send_alert = options["alert"]

        # Check if daily billing task ran
        cutoff = timezone.now() - timedelta(hours=hours)
        recent_runs = BillingAuditLog.objects.filter(
            created_at__gte=cutoff, action_type="AUTO_GENERATE"
        ).count()

        if recent_runs == 0:
            error_msg = (
                f"❌ CRITICAL: Billing queue didn't run in {hours} hours! "
                f"Last check: {cutoff}. No AUTO_GENERATE logs found."
            )
            self.stdout.write(self.style.ERROR(error_msg))
            logger.critical(error_msg)

            if send_alert:
                self._send_alert(error_msg)

            raise CommandError(error_msg)
        else:
            success_msg = (
                f"✓ Celery Health: OK. "
                f"Billing queue ran {recent_runs} time(s) in last {hours}h"
            )
            self.stdout.write(self.style.SUCCESS(success_msg))
            logger.info(success_msg)

    def _send_alert(self, message):
        """
        Send alert to monitoring system.
        Integrate with your monitoring service here:
        - Sentry, Datadog, PagerDuty, Slack, etc.
        """
        try:
            # Example: Send to Slack
            # from django.conf import settings
            # if hasattr(settings, 'SLACK_WEBHOOK_URL'):
            #     requests.post(settings.SLACK_WEBHOOK_URL, json={"text": message})

            # Example: Sentry
            # import sentry_sdk
            # sentry_sdk.capture_message(message, level="critical")

            logger.error(f"Alert triggered: {message}")
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
