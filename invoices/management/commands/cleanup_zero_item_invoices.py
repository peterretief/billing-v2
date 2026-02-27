"""
Management command to delete invoices with zero billed items but non-zero total_amount.
These are clearly corrupted by admin deletions of items that bypassed signals.

Usage:
    python manage.py cleanup_zero_item_invoices --dry-run  # Preview
    python manage.py cleanup_zero_item_invoices --confirm  # Delete
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from invoices.models import Invoice


class Command(BaseCommand):
    help = "Delete invoices with zero items but non-zero total_amount (corrupted by admin deletion)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually delete the corrupted invoices",
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

        # Find invoices with 0 items but non-zero total_amount
        corrupted = []
        for invoice in Invoice.objects.prefetch_related("billed_items"):
            item_count = invoice.billed_items.count()
            if item_count == 0 and invoice.total_amount > Decimal("0.00"):
                # Skip DRAFT and CANCELLED (they can legitimately have 0 items)
                if invoice.status not in ["DRAFT", "CANCELLED"]:
                    corrupted.append(invoice)

        if not corrupted:
            self.stdout.write(self.style.SUCCESS("✓ No corrupted invoices found!"))
            return

        self.stdout.write(f"\nFound {len(corrupted)} corrupted invoices (0 items but non-zero total):\n")
        for inv in corrupted:
            self.stdout.write(
                f"  - {inv.number}: R{inv.total_amount} ({inv.client.name})"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\n[DRY RUN] Would delete {len(corrupted)} corrupted invoices"
                )
            )
            return

        if confirm:
            response = input(
                f"\nType 'DELETE' to confirm deletion of {len(corrupted)} invoices: "
            )
            if response.strip() != "DELETE":
                self.stdout.write(self.style.ERROR("Deletion cancelled."))
                return

            invoice_ids = [inv.id for inv in corrupted]
            invoice_numbers = [inv.number for inv in corrupted]
            Invoice.objects.filter(id__in=invoice_ids).delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Successfully deleted {len(corrupted)} corrupted invoices: "
                    f"{', '.join(invoice_numbers)}"
                )
            )
