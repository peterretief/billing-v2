"""
Django management command to verify billing system data integrity.
Catches silent failures: wrong totals, orphaned records, VAT mismatches, etc.
Run before deployments or on a schedule.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum, Q

from invoices.models import Invoice, Payment
from items.models import Item


class Command(BaseCommand):
    help = "Check invoice system integrity - catches silent data corruption"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Attempt to fix issues (currently logs only, no auto-fix)",
        )
        parser.add_argument(
            "--user",
            type=str,
            help="Check only invoices for specific user (username)",
        )

    def handle(self, *args, **options):
        self.issues = []
        self.warnings = []
        self.fixes_attempted = []

        self.stdout.write(self.style.SUCCESS("🔍 Starting billing system integrity check...\n"))

        # Get invoices to check
        invoices = Invoice.objects.all()
        if options["user"]:
            invoices = invoices.filter(user__username=options["user"])
            self.stdout.write(f"Checking only user: {options['user']}\n")

        invoice_count = invoices.count()
        self.stdout.write(f"Checking {invoice_count} invoices...\n")

        # Run all checks
        self.check_invoice_totals(invoices)
        self.check_orphaned_items()
        self.check_payment_reconciliation(invoices)
        self.check_vat_consistency(invoices)
        self.check_orphaned_payments()
        self.check_duplicate_payments()

        # Report results
        self.print_results()

    def check_invoice_totals(self, invoices):
        """Verify each invoice total matches sum of its items."""
        self.stdout.write("\n📋 Checking invoice totals vs line items...")
        
        for invoice in invoices:
            # Calculate total from billed items
            items_total = Decimal("0.00")
            for item in invoice.billed_items.all():
                items_total += item.quantity * item.unit_price
            
            if invoice.total_amount != items_total:
                self.issues.append(
                    f"Invoice {invoice.number} (ID:{invoice.id}): "
                    f"total_amount={invoice.total_amount} but items sum={items_total}"
                )

        if not self.issues:
            self.stdout.write(self.style.SUCCESS("✓ All invoice totals match line items"))
        
        return len(self.issues) == 0

    def check_orphaned_items(self):
        """Verify no items exist without an invoice."""
        self.stdout.write("\n🔗 Checking for orphaned items...")
        
        orphaned = Item.objects.filter(invoice__isnull=True).count()
        if orphaned > 0:
            self.issues.append(f"Found {orphaned} items with no invoice (orphaned)")
        else:
            self.stdout.write(self.style.SUCCESS("✓ No orphaned items found"))

    def check_payment_reconciliation(self, invoices):
        """Verify payments match invoice balances."""
        self.stdout.write("\n💰 Checking payment reconciliation...")
        
        for invoice in invoices:
            total_paid = invoice.payments.aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0.00")
            
            expected_balance = invoice.total_amount - total_paid
            
            if invoice.balance_due != expected_balance:
                self.issues.append(
                    f"Invoice {invoice.number} (ID:{invoice.id}): "
                    f"balance_due={invoice.balance_due} but expected={expected_balance} "
                    f"(total={invoice.total_amount}, paid={total_paid})"
                )
            
            # Check status consistency
            if invoice.status == "PAID" and invoice.balance_due != Decimal("0.00"):
                self.issues.append(
                    f"Invoice {invoice.number} (ID:{invoice.id}): "
                    f"Status is PAID but balance_due={invoice.balance_due}"
                )
            
            if invoice.status != "PAID" and invoice.balance_due == Decimal("0.00"):
                self.warnings.append(
                    f"Invoice {invoice.number} (ID:{invoice.id}): "
                    f"Status is {invoice.status} but balance_due is 0 (should auto-update to PAID?)"
                )
        
        if not self.issues:
            self.stdout.write(self.style.SUCCESS("✓ All payments reconcile correctly"))

    def check_vat_consistency(self, invoices):
        """Verify VAT calculations are consistent."""
        self.stdout.write("\n🧮 Checking VAT consistency...")
        
        # Get VAT-registered users only
        vat_invoices = invoices.filter(user__profile__is_vat_registered=True)
        
        if not vat_invoices.exists():
            self.stdout.write(self.style.WARNING("⚠ No VAT-registered invoices to check"))
            return
        
        # For now, just verify tax_amount field exists and is not negative
        for invoice in vat_invoices:
            if invoice.tax_amount < Decimal("0.00"):
                self.issues.append(
                    f"Invoice {invoice.number} (ID:{invoice.id}): "
                    f"tax_amount is negative ({invoice.tax_amount})"
                )
            
            # Check that tax_amount is reasonable relative to total_amount
            if invoice.tax_amount > invoice.total_amount:
                self.issues.append(
                    f"Invoice {invoice.number} (ID:{invoice.id}): "
                    f"tax_amount ({invoice.tax_amount}) exceeds total_amount ({invoice.total_amount})"
                )
        
        if not self.issues:
            self.stdout.write(self.style.SUCCESS("✓ All VAT amounts reasonable"))

    def check_orphaned_payments(self):
        """Verify no payments exist without an invoice."""
        self.stdout.write("\n🔗 Checking for orphaned payments...")
        
        orphaned = Payment.objects.filter(invoice__isnull=True).count()
        if orphaned > 0:
            self.issues.append(f"Found {orphaned} payments with no invoice (orphaned)")
        else:
            self.stdout.write(self.style.SUCCESS("✓ No orphaned payments found"))

    def check_duplicate_payments(self):
        """Check for duplicate payments (same amount, same invoice, same day)."""
        self.stdout.write("\n🔄 Checking for duplicate payments...")
        
        from django.db.models import Count
        from datetime import timedelta
        from django.utils import timezone
        
        today = timezone.now().date()
        recent_payments = Payment.objects.filter(
            created_at__date__gte=today - timedelta(days=30)
        )
        
        # Group by invoice + amount + date, find duplicates
        duplicates = (
            recent_payments.values("invoice", "amount", "created_at__date")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        
        if duplicates.exists():
            for dup in duplicates:
                self.warnings.append(
                    f"Possible duplicate: Invoice ID {dup['invoice']}, "
                    f"Amount {dup['amount']}, Date {dup['created_at__date']} "
                    f"({dup['count']} payments)"
                )
        else:
            self.stdout.write(self.style.SUCCESS("✓ No duplicate payments detected"))

    def print_results(self):
        """Print final report."""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("📊 INTEGRITY CHECK RESULTS")
        self.stdout.write("="*60)
        
        if self.issues:
            self.stdout.write(
                self.style.ERROR(f"\n❌ CRITICAL ISSUES FOUND ({len(self.issues)}):\n")
            )
            for issue in self.issues:
                self.stdout.write(self.style.ERROR(f"  ✗ {issue}"))
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ No critical issues found"))
        
        if self.warnings:
            self.stdout.write(
                self.style.WARNING(f"\n⚠️ WARNINGS ({len(self.warnings)}):\n")
            )
            for warning in self.warnings:
                self.stdout.write(self.style.WARNING(f"  ! {warning}"))
        
        self.stdout.write("\n" + "="*60)
        
        if self.issues:
            self.stdout.write(
                self.style.ERROR(
                    f"\n🚨 {len(self.issues)} critical issue(s) detected!\n"
                    "Review above and consider restoring from backup.\n"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("\n✨ System integrity check passed!\n")
            )
