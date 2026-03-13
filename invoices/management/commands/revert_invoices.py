import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from invoices.models import Invoice, InvoiceEmailStatusLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Revert incorrectly sent invoices back to DRAFT (unsent) status"

    def add_arguments(self, parser):
        parser.add_argument(
            "--client",
            type=str,
            help="Revert invoices only for this client name (partial match)",
        )
        parser.add_argument(
            "--user",
            type=str,
            help="Revert invoices only for this user (username or email)",
        )
        parser.add_argument(
            "--invoice-id",
            type=int,
            help="Revert a specific invoice by ID",
        )
        parser.add_argument(
            "--status",
            type=str,
            default="PENDING",
            help="Only revert invoices with this status (default: PENDING)",
        )
        parser.add_argument(
            "--clear-logs",
            action="store_true",
            help="Also clear all email delivery logs for reverted invoices",
        )
        parser.add_argument(
            "--list-only",
            action="store_true",
            help="Show which invoices would be reverted without making changes",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        # Build filter
        filters = {}
        if options["status"]:
            filters["status"] = options["status"]

        if options["invoice_id"]:
            filters["id"] = options["invoice_id"]
        else:
            if options["user"]:
                try:
                    user = User.objects.get(username=options["user"]) or User.objects.get(email=options["user"])
                    filters["user"] = user
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"User '{options['user']}' not found"))
                    return

            if options["client"]:
                filters["client__name__icontains"] = options["client"]

        # Find invoices
        invoices = Invoice.objects.filter(**filters).order_by("-date_issued")

        if not invoices.exists():
            self.stdout.write(self.style.WARNING("No invoices found matching criteria"))
            return

        self.stdout.write(f"\nFound {invoices.count()} invoice(s) to revert:\n")
        self.stdout.write(f"{'ID':<8} {'Client':<25} {'Amount':<12} {'Status':<10} {'Email Logs':<12}")
        self.stdout.write("-" * 70)

        for inv in invoices:
            logs_count = inv.delivery_logs.count()
            self.stdout.write(
                f"{inv.id:<8} {inv.client.name:<25} R{inv.total_amount:<11.2f} {inv.status:<10} {logs_count:<12}"
            )

        if options["list_only"]:
            self.stdout.write(self.style.WARNING("\n(--list-only flag set, no changes made)\n"))
            return

        # Confirm before proceeding
        confirm = input("\nProceed with reverting these invoices to DRAFT? (yes/no): ").strip().lower()
        if confirm != "yes":
            self.stdout.write(self.style.WARNING("Operation cancelled"))
            return

        # Revert invoices
        reverted = 0
        logs_cleared = 0

        for inv in invoices:
            try:
                # Clear delivery logs if requested
                if options["clear_logs"]:
                    logs_count = inv.delivery_logs.count()
                    inv.delivery_logs.all().delete()
                    logs_cleared += logs_count
                    logger.info(f"Cleared {logs_count} delivery logs for invoice {inv.id}")

                # Revert to DRAFT
                inv.status = Invoice.Status.DRAFT
                inv.is_emailed = False
                inv.emailed_at = None
                inv.last_generated = None  # Clear send timestamp for clean restart
                inv.save(update_fields=["status", "is_emailed", "emailed_at", "last_generated"])

                reverted += 1
                logger.info(f"Reverted invoice {inv.id} to DRAFT status")

                self.stdout.write(
                    self.style.SUCCESS(f"✓ Invoice {inv.id} ({inv.client.name}) - Successfully reverted to DRAFT")
                )
            except Exception as e:
                logger.error(f"Failed to revert invoice {inv.id}: {e}")
                self.stdout.write(self.style.ERROR(f"✗ Invoice {inv.id} - Error: {e}"))

        self.stdout.write(f"\n{self.style.SUCCESS('Summary:')}")
        self.stdout.write(f"  ✓ {reverted} invoice(s) reverted to DRAFT")
        if options["clear_logs"]:
            self.stdout.write(f"  ✓ {logs_cleared} delivery log(s) cleared")
        self.stdout.write()
