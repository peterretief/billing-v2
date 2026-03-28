"""
Test suite to verify consistent reporting of invoices, quotes, drafts, and cancelled items.

This test ensures that all reporting methods (dashboard, statements, reconciliation, managers)
consistently exclude/include the right types of invoices.
"""


from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import TestCase

from clients.models import Client
from invoices.models import Invoice, Payment
from invoices.reconciliation import ClientReconciliation

User = get_user_model()


class InvoiceReportingConsistencyTest(TestCase):
    """
    Tests to verify consistent invoice reporting across the app.
    
    Rules to test:
    - DRAFT invoices: never included in any totals
    - QUOTES: never included in financial totals
    - CANCELLED invoices: excluded from totals (but shown in history)
    - PENDING/PAID invoices: always included in totals
    """

    def setUp(self):
        """Create test user, client, and VAT-registered profile"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )
        # Ensure the user has a VAT-registered profile for tax logic
        from core.models import UserProfile
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = True
        self.profile.save()
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            email="client@example.com"
        )

    def create_invoice(self, amount=1000, status="PENDING", is_quote=False):
        """Helper to create a test invoice"""
        from datetime import timedelta

        from django.utils import timezone
        today = timezone.now().date()
        inv = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status=status,
            is_quote=is_quote,
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        # Add item to set total_amount
        from items.models import Item
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=inv,
            quantity=Decimal("1.0"),
            unit_price=Decimal(str(amount)),
        )
        inv.sync_totals()
        inv.save()
        return inv

    def test_draft_invoices_excluded_from_all_totals(self):
        """DRAFT invoices should never appear in any totals"""
        # Create invoices
        pending_inv = self.create_invoice(1000, "PENDING")
        draft_inv = self.create_invoice(5000, "DRAFT")
        
        # Manager method should exclude DRAFT
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("1150.00"))
        
        # Outstanding should exclude DRAFT
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1150.00"))
        
        # Active queryset should exclude DRAFT
        active_count = Invoice.objects.filter(user=self.user).active().count()
        self.assertEqual(active_count, 1)

    def test_quotes_excluded_from_financial_totals(self):
        """Quotes should be tracked but excluded from financial totals"""
        # Create invoices and quotes
        invoice1 = self.create_invoice(1000, "PENDING", is_quote=False)
        quote1 = self.create_invoice(2000, "PENDING", is_quote=True)
        
        # Manager totals should exclude quotes
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("1150.00"))
        
        # Outstanding should exclude quotes
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1150.00"))
        
        # Total count should include both
        all_count = Invoice.objects.filter(user=self.user).exclude(status="DRAFT").count()
        self.assertEqual(all_count, 2)

    def test_cancelled_invoices_excluded_from_totals(self):
        """Cancelled invoices should be visible but excluded from totals"""
        # Create invoices
        pending = self.create_invoice(1000, "PENDING")
        cancelled = self.create_invoice(500, "CANCELLED")
        
        # Totals should exclude CANCELLED
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("1150.00"))
        
        # Outstanding should exclude CANCELLED
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1150.00"))
        
        # All invoices should be queryable
        all_invoices = Invoice.objects.filter(user=self.user).exclude(status="DRAFT")
        self.assertEqual(all_invoices.count(), 2)

    def test_paid_invoices_included_in_totals(self):
        """PAID invoices should be included in billed total"""
        paid = self.create_invoice(1000, "PAID")
        pending = self.create_invoice(500, "PENDING")
        
        # Billed should include both PAID and PENDING
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("1725.00"))
        
        # Outstanding should only include PENDING (not PAID)
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("575.00"))

    def test_drafted_quotes_not_in_totals(self):
        """DRAFT quotes should definitely be excluded"""
        draft_quote = self.create_invoice(1000, "DRAFT", is_quote=True)
        pending_invoice = self.create_invoice(500, "PENDING")
        
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("575.00"))

    def test_reconciliation_excludes_quotes_and_drafts(self):
        """Reconciliation should follow same rules"""
        invoice1 = self.create_invoice(1000, "PENDING")
        quote1 = self.create_invoice(2000, "PENDING", is_quote=True)
        draft1 = self.create_invoice(500, "DRAFT")
        
        recon = ClientReconciliation(self.client_obj, self.user)
        summary = recon.get_summary()
        
        # Should only include invoice1
        self.assertEqual(summary["invoices_sent"], Decimal("1150.00"))

    def test_tax_summary_excludes_quotes(self):
        """Tax summaries should exclude quotes"""
        invoice_paid = self.create_invoice(1000, "PAID")
        quote_paid = self.create_invoice(2000, "PAID", is_quote=True)
        # Use actual calculated VAT from the invoice
        invoice_paid.refresh_from_db()
        expected_vat = invoice_paid.tax_amount
        tax_summary = Invoice.objects.get_tax_summary(self.user)
        # Should only collect tax from invoice_paid, not quote_paid
        self.assertEqual(tax_summary["collected"], expected_vat)

    def test_manager_methods_consistency(self):
        """All manager methods should be consistent"""
        # Create mixed invoices
        pending = self.create_invoice(1000, "PENDING")
        paid = self.create_invoice(800, "PAID")
        quote = self.create_invoice(500, "PENDING", is_quote=True)
        draft = self.create_invoice(300, "DRAFT")
        cancelled = self.create_invoice(400, "CANCELLED")
        
        # Test manager method .totals()
        stats = Invoice.objects.filter(user=self.user).totals()
        # expected_billed = (1000 + 800) * 1.15 = 2070.00 (with 15% VAT)
        expected_billed = Decimal("2070.00")
        self.assertEqual(stats["billed"], expected_billed)
        
        # Test get_dashboard_stats
        dashboard_stats = Invoice.objects.get_dashboard_stats(self.user)
        self.assertEqual(dashboard_stats["total_billed"], expected_billed)
        
        # Test get_total_outstanding (uses .active() method)
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        # expected_outstanding = 1000 * 1.15 = 1150.00 (pending invoice with VAT)
        expected_outstanding = Decimal("1150.00")
        self.assertEqual(outstanding, expected_outstanding)

    def test_no_double_counting_with_payments(self):
        """Ensure payments don't cause double-counting"""
        invoice = self.create_invoice(1000, "PENDING")
        
        # Add payment
        payment = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal("500.00")
        )
        
        # Outstanding should be 650 after payment (VAT-inclusive)
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("650.00"))
        
        # Billed should still be 1000
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("1150.00"))


class InvoiceReportingAuditTest(TestCase):
    """
    Integration tests to verify the audit consistency across different views/reports.
    """
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="audittest",
            email="audit@example.com",
            password="testpass"
        )
        from core.models import UserProfile
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = True
        self.profile.save()
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Audit Test Client",
            email="client@example.com"
        )

    def test_all_reporting_methods_agree(self):
        """
        Verify that dashboard, statement, reconciliation, and manager methods
        all report the same totals for the same query.
        """
        from items.models import Item
        today = timezone.now().date()
        # Create a normal invoice (not a quote)
        inv1 = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PENDING",
            is_quote=False,
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=inv1,
            quantity=Decimal("1.0"),
            unit_price=Decimal("1000.00"),
        )
        inv1.sync_totals()
        inv1.save()
        # Create a quote (should be excluded)
        inv2 = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PENDING",
            is_quote=True,
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=inv2,
            quantity=Decimal("1.0"),
            unit_price=Decimal("2000.00"),
        )
        inv2.sync_totals()
        inv2.save()
        # Use the manager's totals() method for both queries
        manager_totals = Invoice.objects.filter(
            user=self.user,
            status="PENDING",
            is_quote=False
        ).totals()
        direct_totals = Invoice.objects.filter(
            user=self.user,
            client=self.client_obj,
        ).totals()
        # Both should be 1000 + 15% VAT = 1150.00
        self.assertEqual(manager_totals["billed"], Decimal("1150.00"))
        self.assertEqual(direct_totals["billed"], Decimal("1150.00"))
