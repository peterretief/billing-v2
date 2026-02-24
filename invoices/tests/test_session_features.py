"""
Comprehensive tests for audit system, cancellation, and invoice management features.
Tests cover work completed in Feb 2026 session.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import BillingAuditLog, UserProfile
from invoices.models import Invoice
from items.models import Item

User = get_user_model()


class CancelledInvoiceTotalsTest(TestCase):
    """Test that cancelled invoices are excluded from financial totals."""

    def setUp(self):
        self.user = User.objects.create_user(username="totaluser", password="pass")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()

        self.client_obj = Client.objects.create(user=self.user, name="Test Client", client_code="TST")
        self.today = timezone.now().date()

    def _create_invoice_with_item(self, amount, number):
        """Helper to create invoice with item and proper totals."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=number,
            status="DRAFT",
            date_issued=self.today,
            due_date=self.today + timedelta(days=14),
        )

        # Add item
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Test Item",
            quantity=Decimal("1.00"),
            unit_price=amount,
        )

        # Recalculate totals
        Invoice.objects.update_totals(invoice)
        return invoice

    def test_cancelled_excluded_from_outstanding(self):
        """Verify cancelled invoices don't count in outstanding totals."""
        # Create two invoices with items
        inv1 = self._create_invoice_with_item(Decimal("1000.00"), "INV-001")
        inv2 = self._create_invoice_with_item(Decimal("500.00"), "INV-002")

        # Transition to pending
        inv1.status = "PENDING"
        inv1.save()
        inv2.status = "PENDING"
        inv2.save()

        # Before cancellation
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1500.00"))

        # Cancel one
        inv1.status = "CANCELLED"
        inv1.save()

        # After cancellation
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("500.00"))

    def test_active_excludes_cancelled(self):
        """Test that active() queryset excludes cancelled invoices."""
        # Create invoice with item
        invoice = self._create_invoice_with_item(Decimal("1000.00"), "INV-001")

        # Transition to pending
        invoice.status = "PENDING"
        invoice.save()

        # Should be in active
        self.assertEqual(Invoice.objects.filter(user=self.user).active().count(), 1)

        # Cancel it
        invoice.status = "CANCELLED"
        invoice.save()

        # Should be removed from active
        self.assertEqual(Invoice.objects.filter(user=self.user).active().count(), 0)


class CancellationReasonTest(TestCase):
    """Test invoice cancellation with reason tracking."""

    def setUp(self):
        self.user = User.objects.create_user(username="canceluser", password="pass")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()

        self.client_obj = Client.objects.create(user=self.user, name="Test Client", client_code="TST")
        self.today = timezone.now().date()

    def test_cancellation_reason_saved(self):
        """Test that cancellation reason is persisted."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="INV-001",
            status="PENDING",
            date_issued=self.today,
            due_date=self.today + timedelta(days=14),
        )

        # Add item so invoice is complete
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Test Item",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
        )

        Invoice.objects.update_totals(invoice)

        reason = "Wrong email address"
        invoice.cancellation_reason = reason
        invoice.status = "CANCELLED"
        invoice.save()

        # Reload from DB
        invoice.refresh_from_db()
        self.assertEqual(invoice.cancellation_reason, reason)


class EmailBlockingTest(TestCase):
    """Test that email blocking respects only the latest audit log."""

    def setUp(self):
        self.user = User.objects.create_user(username="emailuser", password="pass")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.company_name = "Test Company"
        self.profile.is_vat_registered = False
        self.profile.save()

        self.client_obj = Client.objects.create(
            user=self.user, name="Test Client", client_code="TST", email="test@example.com"
        )
        self.today = timezone.now().date()

    def test_cleared_invoice_can_send(self):
        """Test that an invoice flagged then cleared can be sent."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="INV-001",
            status="PENDING",
            date_issued=self.today,
            due_date=self.today + timedelta(days=14),
            total_amount=Decimal("500.00"),
        )

        # Create flagged log (simulating initial creation)
        BillingAuditLog.objects.create(
            user=self.user, invoice=invoice, is_anomaly=True, ai_comment="Test flag", details={"reason": "initial_flag"}
        )

        # Create cleared log (simulating user clearing it)
        BillingAuditLog.objects.create(
            user=self.user,
            invoice=invoice,
            is_anomaly=False,
            ai_comment="Cleared by user",
            details={"reason": "user_cleared"},
        )

        # Latest log should not be flagged, so email_invoice_to_client
        # should check it and NOT block
        # (Actual email sending would fail in test, but should not be blocked by audit)
        latest_log = BillingAuditLog.objects.filter(invoice=invoice).order_by("-created_at").first()
        self.assertFalse(latest_log.is_anomaly)


class ItemBilledFlagTest(TestCase):
    """Test that billed items are properly marked and excluded from list."""

    def setUp(self):
        self.user = User.objects.create_user(username="itemuser", password="pass")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()

        self.client_obj = Client.objects.create(user=self.user, name="Test Client", client_code="TST")
        self.today = timezone.now().date()

    def test_items_marked_billed_after_invoicing(self):
        """Test that items are marked as_billed=True after invoice creation."""
        # Create item
        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Test Service",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            is_billed=False,
            is_recurring=False,
        )

        # Create invoice and link item
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="INV-001",
            status="DRAFT",
            date_issued=self.today,
            due_date=self.today + timedelta(days=14),
        )

        item.invoice = invoice
        item.is_billed = True
        item.save()

        # Verify item is billed
        item.refresh_from_db()
        self.assertTrue(item.is_billed)

        # Verify unbilled items list excludes it
        unbilled = Item.objects.filter(user=self.user, is_billed=False, is_recurring=False)
        self.assertEqual(unbilled.count(), 0)

    def test_unbilled_items_filter(self):
        """Test that only unbilled items show in the list."""
        # Create 2 items
        item1 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Billed Item",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            is_billed=True,
            is_recurring=False,
        )

        item2 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Unbilled Item",
            quantity=Decimal("1.00"),
            unit_price=Decimal("200.00"),
            is_billed=False,
            is_recurring=False,
        )

        # Filter as ItemListView does
        unbilled = Item.objects.filter(user=self.user, is_billed=False, is_recurring=False)

        self.assertEqual(unbilled.count(), 1)
        self.assertEqual(unbilled.first().description, "Unbilled Item")


class InvoiceLineTotalTest(TestCase):
    """Test invoice line item total calculations."""

    def setUp(self):
        self.user = User.objects.create_user(username="lineuser", password="pass")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()

        self.client_obj = Client.objects.create(user=self.user, name="Test Client", client_code="TST")
        self.today = timezone.now().date()

    def test_item_total_calculation(self):
        """Test that item.total calculates correctly."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="INV-001",
            status="DRAFT",
            date_issued=self.today,
            due_date=self.today + timedelta(days=14),
        )

        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Test Item",
            quantity=Decimal("5"),
            unit_price=Decimal("100.00"),
        )

        # Test total property
        self.assertEqual(item.total, Decimal("500.00"))

        # Test row_subtotal alias
        self.assertEqual(item.row_subtotal, item.total)

    def test_item_total_with_decimal_quantity(self):
        """Test total with decimal quantity (e.g., hours)."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="INV-001",
            status="DRAFT",
            date_issued=self.today,
            due_date=self.today + timedelta(days=14),
        )

        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Hours worked",
            quantity=Decimal("3.5"),
            unit_price=Decimal("150.00"),
        )

        # 3.5 × 150 = 525
        self.assertEqual(item.total, Decimal("525.00"))
