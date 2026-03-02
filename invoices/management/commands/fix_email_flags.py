"""
Management command to fix inconsistent is_emailed flags.

Fixes invoices that have delivery logs but is_emailed=False by:
1. Setting is_emailed=True for invoices with delivery logs
2. Setting emailed_at to the timestamp of the first delivery log
3. Repairing DRAFT+delivery_logs orphaned invoices
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from invoices.models import Invoice


class Command(BaseCommand):
    help = "Fix inconsistent email flags on invoices"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fixed without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        
        if dry_run:
            self.stdout.write("🔍 DRY RUN MODE - No changes will be made\n")
        
        # Find invoices with delivery logs but is_emailed=False
        problematic = Invoice.objects.filter(
            delivery_logs__isnull=False,
            is_emailed=False
        ).distinct()
        
        count = problematic.count()
        self.stdout.write(f"\nFound {count} invoices with delivery logs but is_emailed=False\n")
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS("✅ All invoices have consistent email flags!"))
            return
        
        fixed = 0
        
        for invoice in problematic:
            # Get earliest delivery log
            earliest_log = invoice.delivery_logs.order_by("created_at").first()
            
            if not earliest_log:
                continue
            
            old_state = f"is_emailed={invoice.is_emailed}, emailed_at={invoice.emailed_at}"
            
            # Fix the invoice
            invoice.is_emailed = True
            if not invoice.emailed_at:
                invoice.emailed_at = earliest_log.created_at
            
            if not dry_run:
                invoice.save(update_fields=["is_emailed", "emailed_at"])
            
            new_state = f"is_emailed={invoice.is_emailed}, emailed_at={invoice.emailed_at}"
            self.stdout.write(f"  {invoice.number}: {old_state} → {new_state}")
            fixed += 1
        
        print()
        
        # Also fix DRAFT+delivery_logs orphaned invoices
        orphaned_draft = Invoice.objects.filter(
            status='DRAFT',
            delivery_logs__isnull=False
        ).distinct()
        
        orphaned_count = orphaned_draft.count()
        if orphaned_count > 0:
            self.stdout.write(f"\nFound {orphaned_count} orphaned DRAFT invoices with delivery logs\n")
            
            for invoice in orphaned_draft:
                old_state = f"status={invoice.status}, is_emailed={invoice.is_emailed}"
                
                # Fix via sync method
                corrected = invoice.sync_status_with_delivery()
                
                if corrected and not dry_run:
                    invoice.refresh_from_db()
                
                new_state = f"status={invoice.status}, is_emailed={invoice.is_emailed}"
                self.stdout.write(f"  {invoice.number}: {old_state} → {new_state}")
                fixed += 1
        
        print()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"🔍 Would fix {fixed} invoices. Run without --dry-run to apply changes."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"✅ Fixed {fixed} invoices!")
            )
