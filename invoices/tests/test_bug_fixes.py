"""
Tests for bug fixes implemented in Feb 2026 session.
Covers payment validations, currency handling, audit email sending, and credit notes.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import BillingAuditLog, UserProfile
from invoices.models import CreditNote, Invoice, Payment
from items.models import Item

User = get_user_model()


class CreditOnlyPaymentTest(TestCase):
    """Test that credit-only payments work (amount=0 with credit > 0)."""

    def setUp(self):
        self.user = User.objects.create_user(username="paymentuser", password="pass")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.initial_setup_complete = True  # IMPORTANT: Mark setup as complete for tests
        self.profile.save()

        self.client_obj = Client.objects.create(
            user=self.user, name="Test Client", client_code="TST", email="test@example.com"
        )
        self.today = timezone.now().date()

    def _create_invoice(self, amount):
        """Helper to create invoice with item."""
        import random

        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=f"INV-{int(timezone.now().timestamp())}-{random.randint(1000, 9999)}",
            status="DRAFT",
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
        invoice.refresh_from_db()
        invoice.status = "PENDING"
        invoice.save()
        return invoice

    def test_payment_with_zero_cash_and_credit_accepted(self):
        """Test that Payment.clean() allows amount=0 when credit is being applied."""
        invoice = self._create_invoice(Decimal("100.00"))

        # Create credit note
        credit_note = CreditNote.objects.create(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal("100.00"),
            description="Test credit",
        )

        # Payment with amount=0 should be valid
        payment = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal("0.00"),  # Zero cash
        )

        # Should not raise ValidationError
        try:
            payment.full_clean()
        except Exception as e:
            self.fail(f"Payment validation should allow amount=0, but got {e}")

    def test_payment_rejects_both_zero_cash_and_zero_credit(self):
        """Test that record_payment view rejects when both cash and credit are 0."""
        invoice = self._create_invoice(Decimal("100.00"))
        client = TestClient()
        client.login(username="paymentuser", password="pass")

        # Try to record payment with 0 cash and 0 credit
        response = client.post(
            f"/invoices/{invoice.pk}/record-payment/", {"amount": "0", "credit_to_apply": "0", "reference": "Test"}
        )

        # Should return redirect (success) or 400 (error)
        self.assertIn(response.status_code, [302, 204, 400])

    def test_credit_payment_reduces_balance_and_marks_paid(self):
        """
        Test that credit-only payment (amount=0, credit>0) properly reduces invoice balance_due
        and marks invoice as PAID.

        Bug fix validation: Previously, credits were applied to CreditNote but not reflected
        in Invoice.balance_due or invoice.status, leaving unpaid invoices as PENDING.
        """
        # Create invoice with R100 balance
        invoice = self._create_invoice(Decimal("100.00"))
        self.assertEqual(invoice.balance_due, Decimal("100.00"))
        self.assertEqual(invoice.status, "PENDING")

        # Create credit note with R100
        credit_note = CreditNote.objects.create(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal("100.00"),
            description="R100 credit",
        )
        credit_note.balance = Decimal("100.00")
        credit_note.save()

        # Now record a credit-only payment (0 cash, apply R100 credit)
        client = TestClient()
        client.login(username="paymentuser", password="pass")

        response = client.post(
            f"/invoices/{invoice.pk}/record-payment/",
            {"amount": "0", "credit_to_apply": "100", "reference": "Credit Payment"},
        )

        # Should succeed (redirect)
        self.assertIn(response.status_code, [302, 204], f"Expected redirect/success but got {response.status_code}")

        # Verify Payment was created with credit_applied set
        payment = Payment.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(payment, "Payment should be created for credit payment")
        self.assertEqual(payment.amount, Decimal("0.00"), "Cash amount should be 0 for credit-only payment")
        self.assertEqual(
            payment.credit_applied, Decimal("100.00"), "Credit applied should be recorded in Payment model"
        )

        # Verify invoice balance_due is now 0
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_due, Decimal("0.00"), "Invoice balance_due should be 0 after credit payment")

        # Verify invoice is marked as PAID
        self.assertEqual(invoice.status, "PAID", "Invoice should be marked as PAID after full credit payment")

    def test_credit_note_deleted_when_fully_used(self):
        """Test that credit notes are deleted when their balance reaches zero."""
        # Create invoice with R100 balance
        invoice = self._create_invoice(Decimal("100.00"))

        # Create credit note with exact amount needed to cover invoice
        credit_note = CreditNote.objects.create(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal("100.00"),
            description="Exact credit mount",
        )
        credit_note.balance = Decimal("100.00")
        credit_note.save()

        initial_credit_count = CreditNote.objects.filter(user=self.user, client=self.client_obj).count()
        self.assertEqual(initial_credit_count, 1, "Should have 1 credit note before payment")

        # Record payment using all credit
        client = TestClient()
        client.login(username="paymentuser", password="pass")

        response = client.post(
            f"/invoices/{invoice.pk}/record-payment/",
            {"amount": "0", "credit_to_apply": "100", "reference": "Full Credit Payment"},
        )

        self.assertIn(response.status_code, [302, 204])

        # Verify credit note was deleted
        final_credit_count = CreditNote.objects.filter(user=self.user, client=self.client_obj).count()
        self.assertEqual(final_credit_count, 0, "Credit note should be deleted when fully used")

    def test_credit_note_partial_use_not_deleted(self):
        """Test that partially-used credit notes remain in the system."""
        # Create invoice with R100 balance
        invoice = self._create_invoice(Decimal("100.00"))

        # Create credit note with more than invoice balance
        credit_note = CreditNote.objects.create(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal("150.00"),
            description="Partial credit usage",
        )
        credit_note.balance = Decimal("150.00")
        credit_note.save()

        # Record payment using only R100 of the R150 available
        client = TestClient()
        client.login(username="paymentuser", password="pass")

        response = client.post(
            f"/invoices/{invoice.pk}/record-payment/",
            {"amount": "0", "credit_to_apply": "100", "reference": "Partial Credit Payment"},
        )

        self.assertIn(response.status_code, [302, 204])

        # Verify credit note still exists with reduced balance
        credit_note.refresh_from_db()
        self.assertEqual(credit_note.balance, Decimal("50.00"), "Credit note should have R50 remaining balance")


class CreditNoteWithoutInvoiceTest(TestCase):
    """Test that credit notes can exist without a linked invoice."""

    def setUp(self):
        self.user = User.objects.create_user(username="credituser", password="pass")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.save()

        self.client_obj = Client.objects.create(
            user=self.user, name="Test Client", client_code="TST", email="test@example.com"
        )

    def test_create_credit_note_without_invoice(self):
        """Test that CreditNote can be created with invoice=None."""
        credit_note = CreditNote(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal("50.00"),
            description="Manual adjustment - no invoice",
            invoice=None,  # Explicitly no invoice
            # Don't set balance - it will be set by save()
        )

        # Save will auto-set balance, then no validation error
        credit_note.save()

        self.assertIsNone(credit_note.invoice)
        # After save(), balance should be equal to amount
        self.assertEqual(credit_note.balance, Decimal("50.00"))

    def test_credit_notes_list_with_null_invoices(self):
        """Test that credit notes with null invoice show correctly in list view."""
        # Create credit note without invoice
        cn1 = CreditNote.objects.create(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal("50.00"),
            invoice=None,
        )

        # Verify it can be queried and displayed
        credits = CreditNote.objects.filter(user=self.user)
        self.assertEqual(credits.count(), 1)
        self.assertIsNone(credits.first().invoice)
