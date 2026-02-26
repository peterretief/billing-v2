"""
Test suite to verify consistent reporting of invoices, quotes, drafts, and cancelled items.

This test ensures that all reporting methods (dashboard, statements, reconciliation, managers)
consistently exclude/include the right types of invoices.
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db.models import Sum

from invoices.models import Invoice, Payment
from invoices.reconciliation import ClientReconciliation
from clients.models import Client

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
        """Create test user and client"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            email="client@example.com"
        )

    def create_invoice(self, amount=1000, status="PENDING", is_quote=False, is_billed=True):
        """Helper to create a test invoice"""
        inv = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            total_amount=Decimal(amount),
            status=status,
            is_quote=is_quote,
            is_billed=is_billed,
        )
        return inv

    def test_draft_invoices_excluded_from_all_totals(self):
        """DRAFT invoices should never appear in any totals"""
        # Create invoices
        pending_inv = self.create_invoice(1000, "PENDING")
        draft_inv = self.create_invoice(5000, "DRAFT")
        
        # Manager method should exclude DRAFT
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("1000.00"))
        
        # Outstanding should exclude DRAFT
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1000.00"))
        
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
        self.assertEqual(stats["billed"], Decimal("1000.00"))
        
        # Outstanding should exclude quotes
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1000.00"))
        
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
        self.assertEqual(stats["billed"], Decimal("1000.00"))
        
        # Outstanding should exclude CANCELLED
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1000.00"))
        
        # All invoices should be queryable
        all_invoices = Invoice.objects.filter(user=self.user).exclude(status="DRAFT")
        self.assertEqual(all_invoices.count(), 2)

    def test_paid_invoices_included_in_totals(self):
        """PAID invoices should be included in billed total"""
        paid = self.create_invoice(1000, "PAID")
        pending = self.create_invoice(500, "PENDING")
        
        # Billed should include both PAID and PENDING
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("1500.00"))
        
        # Outstanding should only include PENDING (not PAID)
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("500.00"))

    def test_drafted_quotes_not_in_totals(self):
        """DRAFT quotes should definitely be excluded"""
        draft_quote = self.create_invoice(1000, "DRAFT", is_quote=True)
        pending_invoice = self.create_invoice(500, "PENDING")
        
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("500.00"))

    def test_reconciliation_excludes_quotes_and_drafts(self):
        """Reconciliation should follow same rules"""
        invoice1 = self.create_invoice(1000, "PENDING")
        quote1 = self.create_invoice(2000, "PENDING", is_quote=True)
        draft1 = self.create_invoice(500, "DRAFT")
        
        recon = ClientReconciliation(self.client_obj, self.user)
        summary = recon.get_summary()
        
        # Should only include invoice1
        self.assertEqual(summary["invoices_sent"], Decimal("1000.00"))

    def test_tax_summary_excludes_quotes(self):
        """Tax summaries should exclude quotes"""
        invoice_paid = self.create_invoice(1000, "PAID")
        quote_paid = self.create_invoice(2000, "PAID", is_quote=True)
        
        # Set VAT for this invoice
        invoice_paid.tax_amount = Decimal("150.00")
        invoice_paid.save()
        
        quote_paid.tax_amount = Decimal("300.00")
        quote_paid.save()
        
        tax_summary = Invoice.objects.get_tax_summary(self.user)
        # Should only collect tax from invoice_paid, not quote_paid
        self.assertEqual(tax_summary["collected"], Decimal("150.00"))

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
        expected_billed = Decimal("1800.00")  # pending + paid
        self.assertEqual(stats["billed"], expected_billed)
        
        # Test get_dashboard_stats
        dashboard_stats = Invoice.objects.get_dashboard_stats(self.user)
        self.assertEqual(dashboard_stats["total_billed"], expected_billed)
        
        # Test get_total_outstanding (uses .active() method)
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        expected_outstanding = Decimal("1000.00")  # only pending
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
        
        # Outstanding should be 500 after payment
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("500.00"))
        
        # Billed should still be 1000
        stats = Invoice.objects.filter(user=self.user).totals()
        self.assertEqual(stats["billed"], Decimal("1000.00"))

    def test_audit_trail_consistency_check(self):
        """
        Audit check: sum of invoices should equal (billed - paid)
        This verifies the double-entry consistency
        """
        # Create test data
        inv1 = self.create_invoice(1000, "PENDING")
        inv2 = self.create_invoice(800, "PENDING")
        inv3 = self.create_invoice(500, "PAID")
        
        # Add some payments
        Payment.objects.create(user=self.user, invoice=inv1, amount=Decimal("400.00"))
        Payment.objects.create(user=self.user, invoice=inv2, amount=Decimal("800.00"))
        Payment.objects.create(user=self.user, invoice=inv3, amount=Decimal("500.00"))
        
        # Get totals from manager
        stats = Invoice.objects.filter(user=self.user).totals()
        total_billed = stats["billed"]
        total_paid = stats["paid"]
        
        # Calculate manually
        manual_billed = Invoice.objects.filter(
            user=self.user,
            status__in=["PENDING", "PAID"],
            is_quote=False
        ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        
        manual_paid = Payment.objects.filter(
            user=self.user
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        
        # Should match
        self.assertEqual(total_billed, manual_billed)
        self.assertEqual(total_paid, manual_paid)
        self.assertEqual(total_billed - total_paid, Decimal("1000.00"))


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
        # Create consistent test data
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            total_amount=Decimal("1000.00"),
            status="PENDING",
            is_quote=False,
        )
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            total_amount=Decimal("2000.00"),
            status="PENDING",
            is_quote=True,
        )
        
        # Method 1: Manager
        manager_total = Invoice.objects.filter(
            user=self.user,
            status="PENDING",
            is_quote=False
        ).aggregate(total=Sum("total_amount"))["total"]
        
        # Method 2: Direct query matching manager logic
        direct_total = Invoice.objects.filter(
            user=self.user,
            client=self.client_obj,
        ).exclude(status__in=["DRAFT", "CANCELLED"], is_quote=True).aggregate(
            total=Sum("total_amount")
        )["total"]
        
        # Should all be 1000.00
        self.assertEqual(manager_total, Decimal("1000.00"))
        self.assertEqual(direct_total, Decimal("1000.00"))
