from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice
from items.models import Item

User = get_user_model()


class BillingLogicTest(TestCase):
    """Tests for invoice billing calculations."""

    def setUp(self):
        """Set up shared data for billing tests."""
        self.user = User.objects.create_user(username="tester", password="pass")

        # Explicitly create the profile for the test user
        self.profile, created = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.company_name = "Test Company"
        self.profile.save()

        self.client = Client.objects.create(user=self.user, name="Test Client", client_code="TST")

    def test_standard_timesheet_billing(self):
        """Verify that standard InvoiceItems calculate correctly."""
        today = timezone.now().date()
        invoice = Invoice.objects.create(
            user=self.user, client=self.client, status="DRAFT", date_issued=today, due_date=today + timedelta(days=14)
        )

        # Add a standard item (e.g., 5 hours @ 100)
        Item.objects.create(
            user=self.user,
            client=self.client,
            invoice=invoice,
            description="Development Work",
            quantity=Decimal("5.00"),
            unit_price=Decimal("100.00"),
        )

        invoice.save()
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal("500.00"))
        print(
            f"Standard Billing Success: \
              {invoice.number} total is {invoice.total_amount}"
        )

    def test_vat_calculation(self):
        """Verify that VAT is calculated correctly when enabled."""
        # Enable VAT for the user
        self.profile.is_vat_registered = True
        self.profile.vat_rate = Decimal("15.00")
        self.profile.save()

        today = timezone.now().date()
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            status="DRAFT",
            date_issued=today,
            due_date=today + timedelta(days=14),
            tax_mode=Invoice.TaxMode.FULL,
        )

        Item.objects.create(
            user=self.user,
            client=self.client,
            invoice=invoice,
            description="Consulting",
            quantity=Decimal("10.00"),
            unit_price=Decimal("200.00"),
            is_taxable=True,
        )

        invoice.save()
        invoice.refresh_from_db()

        expected_subtotal = Decimal("2000.00")
        expected_vat = expected_subtotal * (Decimal("15.00") / 100)
        expected_total = expected_subtotal + expected_vat

        self.assertEqual(invoice.calculated_subtotal, expected_subtotal)
        self.assertEqual(invoice.calculated_vat, expected_vat)
        self.assertEqual(invoice.calculated_total, expected_total)

        self.assertEqual(invoice.subtotal_amount, expected_subtotal)
        self.assertEqual(invoice.tax_amount, expected_vat)
        self.assertEqual(invoice.total_amount, expected_total)
        print(f"VAT Billing Success: {invoice.number} total is {invoice.total_amount}")

    def test_resend_invoice_no_recursion(self):
        """
        Verify that resending an invoice does not cause a recursion error.
        """
        # Create an invoice that is already sent
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            status=Invoice.Status.PENDING,
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14),
            total_amount=Decimal("100.00"),  # Set a dummy amount
        )

        # Attempt to save it again, simulating a "resend" action
        try:
            invoice.save()
            # If we get here, there was no recursion error
            self.assertTrue(True)
        except RecursionError:
            self.fail("Resending the invoice caused a RecursionError.")
