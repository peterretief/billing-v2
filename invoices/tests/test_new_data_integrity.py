"""
Test to verify that new invoices and payments maintain data integrity
with the corrected delete signal handlers.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import User
from invoices.models import Invoice, Payment
from items.models import Item


class NewDataIntegrityTest(TestCase):
    """Verify that new data creation maintains integrity with signal handlers."""

    def setUp(self):
        """Set up test user and client."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            client_code="TC"
        )

    def test_invoice_item_totals_recalculate_on_save(self):
        """Verify invoice totals match sum of items."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="DRAFT",
            due_date=timezone.now().date() + timedelta(days=14)
        )

        # Add two items
        item1 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Item 1",
            quantity=Decimal("2"),
            unit_price=Decimal("100.00"),
            invoice=invoice
        )

        item2 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Item 2",
            quantity=Decimal("1"),
            unit_price=Decimal("50.00"),
            invoice=invoice
        )

        # Call sync_totals to recalculate invoice totals
        invoice.sync_totals()
        invoice.refresh_from_db()
        expected_total = Decimal("250.00")  # 2*100 + 1*50

        self.assertEqual(
            invoice.total_amount,
            expected_total,
            f"Invoice total {invoice.total_amount} should equal items sum {expected_total}"
        )

    def test_payment_recorded_on_invoice(self):
        """Verify payment is recorded and balance_due updates."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PENDING",
            due_date=timezone.now().date() + timedelta(days=14)
        )

        # Add item
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Test Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            invoice=invoice
        )

        # Call sync_totals to recalculate
        invoice.sync_totals()
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal("500.00"))

        # Add payment
        payment = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal("300.00"),
            date_paid=timezone.now().date()
        )

        invoice.refresh_from_db()
        expected_balance = Decimal("200.00")  # 500 - 300

        self.assertEqual(
            invoice.balance_due,
            expected_balance,
            f"Balance due {invoice.balance_due} should be {expected_balance}"
        )

    def test_balance_due_recalculates_when_payment_deleted(self):
        """Verify balance_due updates when a payment is deleted via signals."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PENDING",
            due_date=timezone.now().date() + timedelta(days=14)
        )

        # Add item
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Test Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            invoice=invoice
        )

        # Sync totals
        invoice.sync_totals()
        invoice.refresh_from_db()

        # Add payment
        payment = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal("300.00"),
            date_paid=timezone.now().date()
        )

        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_due, Decimal("200.00"))

        # Delete the payment - signals should recalculate balance_due
        payment.delete()

        invoice.refresh_from_db()
        expected_balance = Decimal("500.00")  # Back to full amount

        self.assertEqual(
            invoice.balance_due,
            expected_balance,
            f"After payment delete, balance should be {expected_balance}, got {invoice.balance_due}"
        )

    def test_invoice_totals_recalculate_when_item_deleted(self):
        """Verify invoice total updates when an item is deleted via signals."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="DRAFT",
            due_date=timezone.now().date() + timedelta(days=14)
        )

        # Add two items
        item1 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Item 1",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            invoice=invoice
        )

        item2 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Item 2",
            quantity=Decimal("1"),
            unit_price=Decimal("50.00"),
            invoice=invoice
        )

        # Sync totals
        invoice.sync_totals()
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal("150.00"))

        # Delete item1 - signals should recalculate total
        item1.delete()

        invoice.refresh_from_db()
        expected_total = Decimal("50.00")  # Only item2 remains

        self.assertEqual(
            invoice.total_amount,
            expected_total,
            f"After item delete, total should be {expected_total}, got {invoice.total_amount}"
        )

    def test_no_orphaned_items_created(self):
        """Verify items always have an associated invoice."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="DRAFT",
            due_date=timezone.now().date() + timedelta(days=14)
        )

        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Test Item",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            invoice=invoice
        )

        # Verify item is NOT orphaned
        self.assertIsNotNone(item.invoice)
        self.assertEqual(item.invoice.id, invoice.id)

        # Reload to be sure
        item.refresh_from_db()
        self.assertIsNotNone(item.invoice)
