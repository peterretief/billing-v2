"""
Management command to audit and report timesheets linked to future calendar events.

Usage:
    python manage.py audit_timesheet_completion
    python manage.py audit_timesheet_completion --fix  # Auto-flag or remove
    python manage.py audit_timesheet_completion --export timesheets.csv
"""

import csv

from django.core.management.base import BaseCommand
from django.utils import timezone

from timesheets.models import TimesheetEntry


class Command(BaseCommand):
    help = "Audit timesheets linked to future calendar events (completion gate violation)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Remove timesheets linked to future events (DESTRUCTIVE)',
        )
        parser.add_argument(
            '--flag',
            action='store_true',
            help='Flag problematic timesheets for review (non-destructive)',
        )
        parser.add_argument(
            '--export',
            type=str,
            help='Export problematic entries to CSV file',
        )

    def handle(self, *args, **options):
        fix_mode = options['fix']
        flag_mode = options['flag']
        export_file = options['export']

        now = timezone.now()
        
        # Find all timesheets linked to events
        all_linked = TimesheetEntry.objects.filter(event__isnull=False).select_related('todo')
        
        # Find problematic ones (linked to future calendar events)
        problematic = []
        for entry in all_linked:
            event = entry.event
            
            # Skip if no calendar event
            if not event.calendar_end_time:
                continue
            
            # Check if calendar event hasn't ended yet
            if event.calendar_end_time > now:
                gap_hours = (event.calendar_end_time - now).total_seconds() / 3600
                
                problematic.append({
                    'entry': entry,
                    'event': event,
                    'gap_hours': gap_hours,
                    'is_billed': entry.is_billed,
                })
        
        # Report
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("TIMESHEET COMPLETION AUDIT")
        self.stdout.write(f"{'='*80}\n")
        self.stdout.write(f"Total timesheets linked to events: {all_linked.count()}")
        self.stdout.write(f"Timesheets linked to FUTURE events: {len(problematic)}\n")
        
        if len(problematic) == 0:
            self.stdout.write(self.style.SUCCESS("✓ No issues found! All timesheets follow the completion gate rule."))
            return
        
        self.stdout.write(self.style.WARNING(f"⚠️  FOUND {len(problematic)} VIOLATIONS\n"))
        
        invoiced_count = sum(1 for p in problematic if p['is_billed'])
        unbilled_count = len(problematic) - invoiced_count
        
        self.stdout.write(f"  Invoiced: {invoiced_count} ❌ CRITICAL - Cannot auto-fix")
        self.stdout.write(f"  Unbilled: {unbilled_count} ⚠️  Can be removed\n")
        
        # List details
        self.stdout.write(f"{'ID':<6} {'Date':<12} {'Hours':<8} {'Event':<25} {'Calendar Ends In':<20} {'Billed':<8}")
        self.stdout.write(f"{'-'*100}")
        
        for p in problematic:
            entry = p['entry']
            status = "YES ❌" if p['is_billed'] else "No  ⚠️"
            gap_str = f"{p['gap_hours']:.1f}h" if p['gap_hours'] > 0 else "Ended"
            
            self.stdout.write(
                f"{entry.id:<6} {str(entry.date):<12} {float(entry.hours):<8.2f} "
                f"{str(p['event'])[:25]:<25} {gap_str:<20} {status:<8}"
            )
        
        # Export if requested
        if export_file:
            self._export_csv(problematic, export_file)
            self.stdout.write(self.style.SUCCESS(f"\n✓ Exported to {export_file}"))
        
        # Fix if requested
        if fix_mode:
            if invoiced_count > 0:
                self.stdout.write(
                    self.style.ERROR(
                        f"\n❌ ERROR: Cannot auto-fix - {invoiced_count} entries are already invoiced!\n"
                        "Please manually review invoices before removing timesheets."
                    )
                )
                return
            
            self._fix_entries(problematic)
            self.stdout.write(self.style.SUCCESS(f"✓ Removed {unbilled_count} problematic unbilled timesheets"))
        
        elif flag_mode:
            # Mark problematic entries for review
            self.stdout.write(self.style.WARNING(
                "\n⚠️  Use --fix to remove unbilled timesheets"
            ))
        
        self.stdout.write(f"\n{'='*80}\n")
    
    def _export_csv(self, problematic, filename):
        """Export problematic timesheets to CSV."""
    
    def _export_csv(self, problematic, filename):
        """Export problematic timesheets to CSV."""
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Timesheet ID', 'Date', 'Hours', 'Event', 'Client', 'Category',
                'Calendar End Time', 'Hours Until End', 'Is Billed', 'Hourly Rate', 'Total'
            ])
            
            for p in problematic:
                entry = p['entry']
                writer.writerow([
                    entry.id,
                    entry.date,
                    float(entry.hours),
                    str(p['event']),
                    entry.client.name if entry.client else '',
                    entry.category.name if entry.category else '',
                    p['event'].calendar_end_time,
                    p['gap_hours'],
                    'Yes' if p['is_billed'] else 'No',
                    float(entry.hourly_rate),
                    float(entry.hours) * float(entry.hourly_rate),
                ])
    
    def _fix_entries(self, problematic):
        """Delete unbilled timesheets linked to future events."""
        for p in problematic:
            if not p['is_billed']:
                entry_id = p['entry'].id
                p['entry'].delete()
                self.stdout.write(f"  ✓ Deleted timesheet #{entry_id}")
