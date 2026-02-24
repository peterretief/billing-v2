from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from invoices.models import Invoice, Payment
from items.models import Item

User = get_user_model()


class PaymentValidationTest(TestCase):
    """Full test suite for Payment validation and Invoice status synchronization."""


def setUp(self):
    self.user = User.objects.create_user(username="test_user", password="password")
    self.client_obj = Client.objects.create(user=self.user, name="Test", client_code="TST")

    # 1. Create the invoice
    self.invoice = Invoice.objects.create(
        user=self.user,
        client=self.client_obj,
        number="INV-TST-001",
        status="SENT",
        date_issued=timezone.now().date(),
        due_date=timezone.now().date() + timedelta(days=14),
    )

    # 2. Add the item
    Item.objects.create(user=self.user, invoice=self.invoice, quantity=Decimal("5.00"), unit_price=Decimal("100.00"))

    # 3. THE FIX: Sync totals and REFRESH from the database
    # This forces the R500.00 to move from the Item into the Invoice record
    self.invoice.sync_totals()
    self.invoice.save()

    # This reloads the 'total_amount' field so balance_due is no longer R0.00
    self.invoice.refresh_from_db()

    def test_payment_under_balance_succeeds(self):
        """Verify that payments under balance due are accepted."""
        self.assertEqual(self.invoice.balance_due, Decimal("500.00"))

        Payment.objects.create(
            user=self.user, invoice=self.invoice, amount=Decimal("200.00"), reference="Partial Payment"
        )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal("300.00"))
        self.assertEqual(self.invoice.status, "SENT")

    def test_payment_equal_to_balance_succeeds(self):
        """Verify that a full payment flips the invoice status to PAID."""
        Payment.objects.create(user=self.user, invoice=self.invoice, amount=Decimal("500.00"), reference="Full Payment")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal("0.00"))
        self.assertEqual(self.invoice.status, "PAID")

    def test_payment_exceeds_balance_rejected(self):
        """Verify that overpayments are caught by model validation."""
        with self.assertRaises(ValidationError) as context:
            payment = Payment(user=self.user, invoice=self.invoice, amount=Decimal("600.00"), reference="Overpayment")
            payment.full_clean()

        self.assertIn("cannot exceed", str(context.exception).lower())

    def test_zero_payment_rejected(self):
        """Verify that zero or negative payments are blocked."""
        with self.assertRaises(ValidationError) as context:
            payment = Payment(user=self.user, invoice=self.invoice, amount=Decimal("0.00"))
            payment.full_clean()
        self.assertIn("greater than zero", str(context.exception).lower())

    def test_multiple_partial_payments(self):
        """Verify multiple payments accumulate correctly."""
        for amt in [Decimal("200.00"), Decimal("150.00"), Decimal("150.00")]:
            Payment.objects.create(user=self.user, invoice=self.invoice, amount=amt)
            self.invoice.refresh_from_db()

        self.assertEqual(self.invoice.balance_due, Decimal("0.00"))
        self.assertEqual(self.invoice.status, "PAID")

    def test_payment_deletion_reverts_status(self):
        """Verify status moves from PAID back to SENT when payment is removed."""
        payment = Payment.objects.create(user=self.user, invoice=self.invoice, amount=Decimal("500.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "PAID")

        payment.delete()

        # Explicitly trigger manager update if no signals are present
        Invoice.objects.update_totals(self.invoice)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "SENT")
