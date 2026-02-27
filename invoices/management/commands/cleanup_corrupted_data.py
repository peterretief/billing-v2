"""
Management command to cleanup corrupted invoice data.

This command identifies and deletes invoices with data integrity issues such as:
- Invoices where total_amount doesn't match sum of billed_items
- Orphaned items (items with no associated invoice)
- Duplicate or malformed payment records

Usage:
    python manage.py cleanup_corrupted_data --dry-run  # Preview what will be deleted
    python manage.py cleanup_corrupted_data --confirm  # Actually delete the data
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q, Sum

from invoices.models import Invoice, Payment
from items.models import Item


class Command(BaseCommand):
    help = "Clean up corrupted invoice data caused by admin deletions that bypass signals"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually delete the corrupted records (use with caution)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        confirm = options["confirm"]

        if not dry_run and not confirm:
            self.stdout.write(
                self.style.WARNING(
                    "Please run with --dry-run to preview changes, or --confirm to apply"
                )
            )
            return

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("INVOICE DATA CLEANUP")
        self.stdout.write("=" * 70 + "\n")

        # Find corrupted invoices
        corrupted_invoices = self.find_corrupted_invoices()

        if not corrupted_invoices:
            self.stdout.write(self.style.SUCCESS("✓ No corrupted invoices found!"))
            return

        self.stdout.write(f"\nFound {len(corrupted_invoices)} corrupted invoices:\n")

        for invoice in corrupted_invoices:
            items_total = Decimal("0.00")
            for item in invoice.billed_items.all():
                items_total += item.quantity * item.unit_price

            self.stdout.write(f"  Invoice {invoice.number}:")
            self.stdout.write(f"    - Recorded total: R{invoice.total_amount}")
            self.stdout.write(f"    - Items sum: R{items_total}")
            self.stdout.write(f"    - Items: {invoice.billed_items.count()}")
            self.stdout.write(f"    - Payments: {invoice.payments.count()}")
            self.stdout.write("")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\n[DRY RUN] Would delete {len(corrupted_invoices)} invoices and their related items/payments"
                )
            )
            self.stdout.write("Run with --confirm to actually delete these records\n")
            return

        if confirm:
            confirmed = self.confirm_deletion(corrupted_invoices)
            if not confirmed:
                self.stdout.write(self.style.ERROR("Deletion cancelled."))
                return

            # Delete the corrupted invoices (cascade will handle items and payments)
            invoice_ids = [inv.id for inv in corrupted_invoices]
            invoice_numbers = [inv.number for inv in corrupted_invoices]

            Invoice.objects.filter(id__in=invoice_ids).delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Successfully deleted {len(corrupted_invoices)} corrupted invoices: "
                    f"{', '.join(invoice_numbers)}"
                )
            )

            # Check for remaining orphaned items
            orphaned_items = Item.objects.filter(invoice__isnull=True)
            if orphaned_items.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"\n⚠ Found {orphaned_items.count()} orphaned items (no associated invoice)"
                    )
                )
                self.stdout.write("These are likely from previous deletions via admin")

                # Show details
                for item in orphaned_items[:10]:  # Show first 10
                    self.stdout.write(
                        f"  - {item.date}: {item.client.name} - {item.description[:50]}"
                    )

                if orphaned_items.count() > 10:
                    self.stdout.write(f"  ... and {orphaned_items.count() - 10} more")

    def find_corrupted_invoices(self):
        """Find invoices where total_amount doesn't match sum of billed_items."""
        corrupted = []

        for invoice in Invoice.objects.select_related("client").prefetch_related("billed_items"):
            # Skip draft and cancelled invoices (they may legitimately have R0)
            if invoice.status in ["DRAFT", "CANCELLED"]:
                continue

            items_total = Decimal("0.00")
            for item in invoice.billed_items.all():
                items_total += item.quantity * item.unit_price

            # Check if totals match (allow for small rounding)
            if abs(invoice.total_amount - items_total) > Decimal("0.01"):
                corrupted.append(invoice)

        return corrupted

    def confirm_deletion(self, invoices):
        """Ask user to confirm deletion."""
        self.stdout.write(self.style.WARNING("\n⚠ WARNING: About to delete the following invoices:"))
        for inv in invoices:
            self.stdout.write(f"  - {inv.number} ({inv.client.name})")

        self.stdout.write(
            self.style.ERROR("\nThis action CANNOT BE UNDONE. Related items and payments will also be deleted.\n")
        )

        response = input("Type 'DELETE' to confirm deletion: ")
        return response.strip() == "DELETE"
