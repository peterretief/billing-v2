"""
Tests for reconciliation payment validation.
Ensures payments (cash + credit) never exceed invoice totals.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from clients.models import Client
from invoices.models import Invoice, Payment
from invoices.reconciliation import ClientReconciliation

User = get_user_model()


class PaymentValidationTest(TestCase):
    """Test that payments cannot exceed invoice amounts."""

    def setUp(self):
        """Create test user, client, and invoice."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client.objects.create(user=self.user, name="Test Client", email="test@example.com")
        self.invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            number="INV-001",
            status="PENDING",
            total_amount=Decimal("1000.00"),
        )

    def test_payment_cash_cannot_exceed_invoice(self):
        """Test that cash payment cannot exceed invoice total."""
        payment = Payment(user=self.user, invoice=self.invoice, amount=Decimal("1100.00"))

        with self.assertRaises(Exception):
            payment.full_clean()

    def test_payment_credit_cannot_cause_total_to_exceed_invoice(self):
        """Test that cash + credit together cannot exceed invoice total."""
        payment = Payment(
            user=self.user,
            invoice=self.invoice,
            amount=Decimal("600.00"),  # $600 cash
            credit_applied=Decimal("500.00"),  # $500 credit = $1100 total
        )

        with self.assertRaises(Exception):
            payment.full_clean()

    def test_valid_payment_with_cash_and_credit(self):
        """Test that valid payment with cash and credit is accepted."""
        payment = Payment(
            user=self.user,
            invoice=self.invoice,
            amount=Decimal("700.00"),  # $700 cash
            credit_applied=Decimal("300.00"),  # $300 credit = $1000 total
        )

        # Should not raise
        payment.full_clean()

    def test_payment_credit_only(self):
        """Test that credit-only payment is valid."""
        payment = Payment(
            user=self.user,
            invoice=self.invoice,
            amount=Decimal("0.00"),  # $0 cash
            credit_applied=Decimal("500.00"),  # $500 credit
        )

        # Should not raise
        payment.full_clean()


class ReconciliationCalcuationTest(TestCase):
    """Test that reconciliation calculations correctly separate cash and credit."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client.objects.create(user=self.user, name="Test Client", email="test@example.com")

        # Create two invoices
        self.invoice1 = Invoice.objects.create(
            user=self.user,
            client=self.client,
            number="INV-001",
            status="PENDING",
            total_amount=Decimal("1000.00"),
            date_issued=date(2026, 1, 1),
        )

        self.invoice2 = Invoice.objects.create(
            user=self.user,
            client=self.client,
            number="INV-002",
            status="PENDING",
            total_amount=Decimal("500.00"),
            date_issued=date(2026, 1, 15),
        )

    def test_reconciliation_separates_cash_and_credit(self):
        """Test that reconciliation summary correctly separates cash and credit payments."""
        # Create payment with cash and credit
        payment1 = Payment.objects.create(
            user=self.user,
            invoice=self.invoice1,
            amount=Decimal("700.00"),  # Cash
            credit_applied=Decimal("300.00"),  # Credit
            date_paid=date(2026, 2, 1),
        )

        # Create a second payment (cash only)
        payment2 = Payment.objects.create(
            user=self.user,
            invoice=self.invoice2,
            amount=Decimal("500.00"),  # Cash
            credit_applied=Decimal("0.00"),
            date_paid=date(2026, 2, 5),
        )

        # Get reconciliation
        recon = ClientReconciliation(self.client, self.user, date(2026, 1, 1), date(2026, 2, 28))
        summary = recon.get_summary()

        # Verify calculations
        assert summary["invoices_sent"] == Decimal("1500.00"), "Should have $1500 in invoices"
        assert summary["payments_received"] == Decimal("1200.00"), "Should have $1200 in cash payments"
        assert summary["credit_in_payments"] == Decimal("300.00"), "Should have $300 in credit applied"

        # Calculate expected closing balance
        # Opening: $0
        # + Invoices: $1500
        # - Cash payments: $1200
        # - Credit applied: $300
        # = Closing: $0
        expected_closing = Decimal("0.00")
        assert summary["closing_balance"] == expected_closing, f"Expected closing balance {expected_closing}, got {summary['closing_balance']}"

    def test_reconciliation_payment_never_exceeds_invoice(self):
        """Test that reconciliation will show correct balances even with credit."""
        # Create a partial cash payment with credit to complete it
        payment = Payment.objects.create(
            user=self.user,
            invoice=self.invoice1,
            amount=Decimal("500.00"),  # $500 cash
            credit_applied=Decimal("500.00"),  # $500 credit = fully paid
            date_paid=date(2026, 2, 1),
        )

        recon = ClientReconciliation(self.client, self.user)
        transactions = recon.get_transactions()

        # Find the payment transaction
        payment_trans = [t for t in transactions if t["type"] == "PAYMENT" and t["payment"].id == payment.id]
        assert len(payment_trans) == 1, "Should have one payment transaction"

        # Verify the payment shows the total
        trans = payment_trans[0]
        assert trans["amount"] == Decimal("-1000.00"), "Payment transaction should show full amount (cash + credit)"
