"""
Tests to verify that cancelled invoices are excluded from all financial totals.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice, Payment
from items.models import Item

User = get_user_model()


class CancelledInvoiceTotalsTest(TestCase):
    """Verify cancelled invoices are excluded from all total calculations."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="tester", password="pass")

        # Create user profile
        self.profile, created = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.company_name = "Test Company"
        self.profile.save()

        self.client = Client.objects.create(user=self.user, name="Test Client", client_code="TST")

        self.today = timezone.now().date()

    def _create_invoice(self, amount=Decimal("1000.00"), status="PENDING", number_suffix="001"):
        """Helper to create an invoice with items."""
        # Use DRAFT first to prevent auto-PAID conversion, then change status
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            number=f"INV-TST-{number_suffix}",
            status="DRAFT",  # Start as DRAFT to avoid auto-conversion
            date_issued=self.today,
            due_date=self.today + timedelta(days=14),
            subtotal_amount=amount,
            tax_amount=Decimal("0.00"),
            total_amount=amount,
        )

        # Add item to represent billable work
        Item.objects.create(
            user=self.user,
            client=self.client,
            invoice=invoice,
            description="Test Service",
            quantity=Decimal("1.00"),
            unit_price=amount,
        )

        # Now change to desired status
        if status != "DRAFT":
            invoice.status = status
            invoice.save(update_fields=["status"])

        return invoice

    def test_cancelled_invoice_excluded_from_get_total_outstanding(self):
        """Verify get_total_outstanding() excludes cancelled invoices."""
        # Create 2 pending invoices: $1000 each
        inv1 = self._create_invoice(Decimal("1000.00"), "PENDING", "001")
        inv2 = self._create_invoice(Decimal("1000.00"), "PENDING", "002")

        # Total outstanding should be $2000
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("2000.00"))

        # Cancel one invoice
        inv1.status = "CANCELLED"
        inv1.save()

        # Total outstanding should now be $1000 (only inv2)
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1000.00"))

    def test_multiple_cancelled_invoices_excluded(self):
        """Verify multiple cancelled invoices are all excluded."""
        # Create 5 pending invoices: $500 each
        invoices = []
        for i in range(5):
            inv = self._create_invoice(Decimal("500.00"), "PENDING", f"{str(i).zfill(3)}")
            invoices.append(inv)

        # Total outstanding should be $2500
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("2500.00"))

        # Cancel 3 invoices
        for i in range(3):
            invoices[i].status = "CANCELLED"
            invoices[i].save()

        # Total outstanding should now be $1000 (only 2 invoices remain)
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1000.00"))

    def test_cancelled_with_payments_excluded(self):
        """Verify that cancelled invoices with payments don't affect totals."""
        # Create and pay a $1000 invoice
        paid_inv = self._create_invoice(Decimal("1000.00"), "PENDING", "001")
        Payment.objects.create(user=self.user, invoice=paid_inv, amount=Decimal("1000.00"), reference="Full Payment")
        paid_inv.status = "PAID"
        paid_inv.save()

        # Create a $500 pending invoice
        pending_inv = self._create_invoice(Decimal("500.00"), "PENDING", "002")

        # Create a $750 cancelled invoice with a payment
        cancelled_inv = self._create_invoice(Decimal("750.00"), "PENDING", "003")
        Payment.objects.create(
            user=self.user, invoice=cancelled_inv, amount=Decimal("500.00"), reference="Partial Payment Before Cancel"
        )
        cancelled_inv.status = "CANCELLED"
        cancelled_inv.save()

        # Outstanding should be $500 (only pending_inv)
        # Paid invoice is excluded, cancelled is excluded regardless of payment
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("500.00"))

    def test_active_queryset_excludes_cancelled(self):
        """Verify that the active() queryset excludes cancelled invoices."""
        # Create 3 invoices with different statuses
        draft_inv = self._create_invoice(Decimal("100.00"), "DRAFT", "001")
        pending_inv = self._create_invoice(Decimal("200.00"), "PENDING", "002")
        cancelled_inv = self._create_invoice(Decimal("300.00"), "PENDING", "003")

        # Cancel one
        cancelled_inv.status = "CANCELLED"
        cancelled_inv.save()

        # active() should only return pending_inv (excludes DRAFT and CANCELLED)
        active_invoices = Invoice.objects.filter(user=self.user).active()
        active_ids = set(active_invoices.values_list("id", flat=True))

        self.assertNotIn(draft_inv.id, active_ids)  # DRAFT excluded
        self.assertIn(pending_inv.id, active_ids)  # PENDING included
        self.assertNotIn(cancelled_inv.id, active_ids)  # CANCELLED excluded

    def test_dashboard_stats_exclude_cancelled(self):
        """Verify dashboard stats calculation excludes cancelled invoices."""
        # Create and pay a $1000 invoice
        paid_inv = self._create_invoice(Decimal("1000.00"), "PENDING", "001")
        Payment.objects.create(user=self.user, invoice=paid_inv, amount=Decimal("1000.00"), reference="Full Payment")
        paid_inv.status = "PAID"
        paid_inv.save()

        # Create a $500 pending invoice
        pending_inv = self._create_invoice(Decimal("500.00"), "PENDING", "002")

        # Create a $750 cancelled invoice
        cancelled_inv = self._create_invoice(Decimal("750.00"), "PENDING", "003")
        cancelled_inv.status = "CANCELLED"
        cancelled_inv.save()

        # Get all active (non-cancelled) invoices
        active_count = Invoice.objects.filter(user=self.user).active().count()

        # Should have 1 active invoice (only pending_inv, not paid or cancelled)
        self.assertEqual(active_count, 1)

    def test_cancelled_invoice_truly_excluded_not_zeroed(self):
        """Verify cancelled invoices don't just have zero amounts - they're excluded."""
        # Create 2 $1000 invoices
        inv1 = self._create_invoice(Decimal("1000.00"), "PENDING", "001")
        inv2 = self._create_invoice(Decimal("1000.00"), "PENDING", "002")

        # Verify both have amounts
        self.assertEqual(inv1.total_amount, Decimal("1000.00"))
        self.assertEqual(inv2.total_amount, Decimal("1000.00"))

        # Cancel one - it should STILL have the amount (not zeroed)
        inv1.status = "CANCELLED"
        inv1.save()
        inv1.refresh_from_db()

        # Verify the cancelled invoice STILL has its amount
        self.assertEqual(inv1.total_amount, Decimal("1000.00"))

        # But outstanding should only include inv2
        outstanding = Invoice.objects.get_total_outstanding(self.user)
        self.assertEqual(outstanding, Decimal("1000.00"))
