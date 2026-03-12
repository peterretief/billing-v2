import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from billing_schedule.tasks import process_daily_billing_queue
from core.models import BillingAuditLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Manually process the daily billing queue. Creates invoices for recurring items and due billing policies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            help="Process billing queue for a specific user only (username or email)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed output",
        )

    def handle(self, *args, **options):
        user_filter = options.get("user")
        verbose = options.get("verbose", False)

        self.stdout.write(self.style.SUCCESS("🔄 Starting billing queue processing..."))

        try:
            if user_filter:
                # Process for specific user
                User = get_user_model()
                try:
                    user = User.objects.get(username=user_filter) or User.objects.get(email=user_filter)
                    from items.services import import_recurring_to_invoices

                    self.stdout.write(f"\n📊 Processing billing queue for user: {user.username}")
                    created_invoices = import_recurring_to_invoices(user)

                    if created_invoices:
                        self.stdout.write(
                            self.style.SUCCESS(f"✅ Created {len(created_invoices)} invoice(s) for {user.username}")
                        )
                        for invoice in created_invoices:
                            self.stdout.write(f"   - {invoice.number}: {invoice.total}")
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"⚠️  No invoices created for {user.username} (no queued items)")
                        )
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"❌ User '{user_filter}' not found"))
                    return
            else:
                # Process for all users (like the scheduled task)
                result = process_daily_billing_queue()
                total_created = sum(len(invoices) for invoices in result if isinstance(invoices, list))

                # Parse the results
                User = get_user_model()
                active_users = User.objects.filter(is_active=True)
                total_result_count = len(result) if isinstance(result, list) else 0

                self.stdout.write(f"\n📊 Processing billing queue for {active_users.count()} active users...")
                self.stdout.write(result if isinstance(result, str) else "\n".join(str(r) for r in result))

                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✅ Billing queue processing complete! Total users processed: {active_users.count()}"
                    )
                )

            # Check audit logs
            recent_logs = BillingAuditLog.objects.filter(action_type="AUTO_GENERATE").order_by(
                "-created_at"
            )[:5]
            if verbose and recent_logs.exists():
                self.stdout.write("\n📝 Recent audit logs:")
                for log in recent_logs:
                    self.stdout.write(f"   {log.created_at} - {log.user.username} - {log.action_type}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error processing billing queue: {str(e)}"))
            logger.exception("Error in process_billing_queue command")
            raise
