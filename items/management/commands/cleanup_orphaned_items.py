"""
Management command to delete orphaned items (items with no associated invoice).

Usage:
    python manage.py cleanup_orphaned_items --dry-run  # Preview
    python manage.py cleanup_orphaned_items --confirm  # Delete
"""

from django.core.management.base import BaseCommand

from items.models import Item


class Command(BaseCommand):
    help = "Delete orphaned items with no associated invoice"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually delete the orphaned items",
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

        orphaned = Item.objects.filter(invoice__isnull=True)
        count = orphaned.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("✓ No orphaned items found!"))
            return

        self.stdout.write(f"\nFound {count} orphaned items:\n")
        for item in orphaned[:15]:
            self.stdout.write(f"  - {item.date}: {item.client.name} - {item.description[:40]}")
        if count > 15:
            self.stdout.write(f"  ... and {count - 15} more")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n[DRY RUN] Would delete {count} orphaned items"))
            return

        if confirm:
            response = input(f"\nType 'DELETE' to confirm deletion of {count} items: ")
            if response.strip() != "DELETE":
                self.stdout.write(self.style.ERROR("Deletion cancelled."))
                return

            orphaned.delete()
            self.stdout.write(self.style.SUCCESS(f"\n✓ Successfully deleted {count} orphaned items"))
