"""
Tests for payment modal auto-population with smart defaults (balance - credit).
Tests that the form automatically populates payment amounts based on available credit.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import CreditNote, Invoice
from items.models import Item

User = get_user_model()


class PaymentModalAutoPopulationTest(TestCase):
    """Test that payment modal auto-populates with smart defaults."""

    def setUp(self):
        self.user = User.objects.create_user(username="modaluser", password="pass")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.initial_setup_complete = True  # Mark setup as complete
        self.profile.save()

        self.client_obj = Client.objects.create(
            user=self.user, name="Test Client", client_code="TST", email="test@example.com"
        )
        self.today = timezone.now().date()
        self.http_client = TestClient()
        self.http_client.login(username="modaluser", password="pass")

    def _create_invoice(self, amount):
        """Helper to create invoice."""
        import random

        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=f"INV-{int(timezone.now().timestamp())}-{random.randint(1000, 9999)}",
            status="PENDING",
            date_issued=self.today,
            due_date=self.today + timedelta(days=14),
        )

        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Test Item",
            quantity=Decimal("1.00"),
            unit_price=amount,
        )

        Invoice.objects.update_totals(invoice)
        return invoice

    def test_payment_modal_shows_available_credit(self):
        """Test that payment modal displays available credit."""
        invoice = self._create_invoice(Decimal("1000.00"))

        # Create credit note
        credit = CreditNote.objects.create(
            user=self.user, client=self.client_obj, note_type=CreditNote.NoteType.ADJUSTMENT, amount=Decimal("300.00")
        )

        # Request payment modal
        response = self.http_client.get(f"/invoices/invoice/{invoice.pk}/payment-modal/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "300.00")  # Available credit
        self.assertIn("available_credit", response.context)
        self.assertEqual(response.context["available_credit"], Decimal("300.00"))

    def test_payment_modal_context_has_data_attributes(self):
        """Test that modal context includes balance and credit in data attributes."""
        invoice = self._create_invoice(Decimal("1000.00"))

        credit = CreditNote.objects.create(
            user=self.user, client=self.client_obj, note_type=CreditNote.NoteType.ADJUSTMENT, amount=Decimal("300.00")
        )

        response = self.http_client.get(f"/invoices/invoice/{invoice.pk}/payment-modal/")

        # Verify context data for JavaScript initialization
        self.assertEqual(response.context["invoice"].balance_due, Decimal("1000.00"))
        self.assertEqual(response.context["available_credit"], Decimal("300.00"))

    def test_payment_modal_partial_credit_scenario(self):
        """Test payment modal when credit is less than balance."""
        balance = Decimal("1000.00")
        credit_amt = Decimal("300.00")

        invoice = self._create_invoice(balance)

        CreditNote.objects.create(
            user=self.user, client=self.client_obj, note_type=CreditNote.NoteType.ADJUSTMENT, amount=credit_amt
        )

        response = self.http_client.get(f"/invoices/invoice/{invoice.pk}/payment-modal/")

        # Modal should show
        self.assertEqual(response.status_code, 200)
        # Context should have the credit available
        self.assertEqual(response.context["available_credit"], credit_amt)
        # Invoice balance should be shown
        self.assertEqual(response.context["invoice"].balance_due, balance)

    def test_payment_modal_full_credit_scenario(self):
        """Test payment modal when credit covers full balance."""
        balance = Decimal("500.00")
        credit_amt = Decimal("600.00")

        invoice = self._create_invoice(balance)

        CreditNote.objects.create(
            user=self.user, client=self.client_obj, note_type=CreditNote.NoteType.ADJUSTMENT, amount=credit_amt
        )

        response = self.http_client.get(f"/invoices/invoice/{invoice.pk}/payment-modal/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["available_credit"], credit_amt)
        # Template should show credit field is available
        self.assertContains(response, "Apply Credit Balance")

    def test_payment_modal_no_credit_scenario(self):
        """Test payment modal when no credit is available."""
        invoice = self._create_invoice(Decimal("1000.00"))

        response = self.http_client.get(f"/invoices/invoice/{invoice.pk}/payment-modal/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["available_credit"], Decimal("0.00"))
        # Should not have credit input field in context
        # (hidden input instead)

    def test_payment_modal_includes_currency(self):
        """Test that payment modal includes user's currency."""
        invoice = self._create_invoice(Decimal("1000.00"))

        response = self.http_client.get(f"/invoices/invoice/{invoice.pk}/payment-modal/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("currency", response.context)
        # Should default to 'R'
        self.assertEqual(response.context["currency"], "R")

    def test_payment_modal_max_button_has_credit_data(self):
        """Test that Max button has data attributes for credit amount."""
        invoice = self._create_invoice(Decimal("1000.00"))

        credit_amt = Decimal("300.00")
        CreditNote.objects.create(
            user=self.user, client=self.client_obj, note_type=CreditNote.NoteType.ADJUSTMENT, amount=credit_amt
        )

        response = self.http_client.get(f"/invoices/invoice/{invoice.pk}/payment-modal/")

        # Check that Max button data is in HTML
        self.assertContains(response, "creditMaxBtn")
        self.assertContains(response, "data-available-credit")
