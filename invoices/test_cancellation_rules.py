"""
Tests for invoice cancellation and payment rules.

Tests that:
1. PAID invoices auto-create credit notes when cancelled
2. Payments cannot exceed invoice amount
3. Payments cannot be added to DRAFT or CANCELLED invoices
"""

from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone

from clients.models import Client
from invoices.models import Invoice, Payment, CreditNote
from items.models import Item

User = get_user_model()


class InvoiceCancellationRulesTest(TestCase):
    """Test invoice cancellation and credit note creation."""

    def setUp(self):
        """Create test user, client, and invoices."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.client = Client.objects.create(
            user=self.user,
            name='Test Client',
            email='client@example.com'
        )

    def _create_invoice_with_amount(self, number, amount, status, due_date=None):
        """Helper to create invoice with items that total to the specified amount."""
        if due_date is None:
            due_date = timezone.now().date() + timedelta(days=14)
        
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            number=number,
            due_date=due_date,
            status=status
        )
        
        # Create an item linked to invoice with quantity * unit_price = amount
        # Use quantity=1 and unit_price=amount for simplicity
        Item.objects.create(
            user=self.user,
            client=self.client,
            description=f"Test item for {number}",
            quantity=Decimal('1'),
            unit_price=amount,
            invoice=invoice
        )
        
        # Manually call update_totals to ensure invoice total_amount is calculated
        Invoice.objects.update_totals(invoice)
        
        # Refresh invoice from DB to get updated total_amount
        invoice.refresh_from_db()
        return invoice

    def test_draft_invoice_cancellation_no_credit(self):
        """DRAFT invoices should cancel without creating credit notes."""
        invoice = self._create_invoice_with_amount(
            'TEST-001',
            Decimal('1000.00'),
            Invoice.Status.DRAFT
        )
        
        # Cancel the draft invoice
        invoice.status = Invoice.Status.CANCELLED
        invoice.save()
        
        # No credit note should be created (no payment was made)
        credits = CreditNote.objects.filter(invoice=invoice)
        self.assertEqual(credits.count(), 0)

    def test_paid_invoice_cancellation_creates_credit(self):
        """PAID invoices should auto-create credit note when cancelled."""
        invoice = self._create_invoice_with_amount(
            'TEST-002',
            Decimal('1000.00'),
            Invoice.Status.PAID
        )
        
        # Add a payment
        payment = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal('1000.00'),
            date_paid='2026-02-25'
        )
        
        # Record initial credit count
        initial_credits = CreditNote.objects.count()
        
        # Cancel the paid invoice
        invoice.status = Invoice.Status.CANCELLED
        invoice.cancellation_reason = "Duplicate invoice"
        invoice.save()
        
        # Credit note should be created
        credits = CreditNote.objects.filter(
            invoice=invoice,
            note_type=CreditNote.NoteType.CANCELLATION
        )
        self.assertEqual(credits.count(), 1)
        
        # Credit amount should match payment
        credit = credits.first()
        self.assertEqual(credit.amount, Decimal('1000.00'))
        self.assertEqual(credit.client_id, self.client.id)

    def test_partial_payment_cancellation_creates_partial_credit(self):
        """Cancelled PAID invoice with partial payment should create matching credit."""
        invoice = self._create_invoice_with_amount(
            'TEST-003',
            Decimal('1000.00'),
            Invoice.Status.PAID
        )
        
        # Add partial payment
        payment = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal('600.00'),
            date_paid='2026-02-25'
        )
        
        # Cancel the invoice
        invoice.status = Invoice.Status.CANCELLED
        invoice.save()
        
        # Credit should match partial payment
        credit = CreditNote.objects.get(invoice=invoice)
        self.assertEqual(credit.amount, Decimal('600.00'))


class PaymentOverpaymentPreventionTest(TestCase):
    """Test that payments cannot exceed invoice amount."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        
        self.client = Client.objects.create(
            user=self.user,
            name='Test Client 2',
            email='client2@example.com'
        )

    def _create_invoice_with_amount(self, number, amount, status, due_date=None):
        """Helper to create invoice with items that total to the specified amount."""
        if due_date is None:
            due_date = timezone.now().date() + timedelta(days=14)
        
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            number=number,
            due_date=due_date,
            status=status
        )
        
        # Create an item linked to invoice with quantity * unit_price = amount
        # Use quantity=1 and unit_price=amount for simplicity
        Item.objects.create(
            user=self.user,
            client=self.client,
            description=f"Test item for {number}",
            quantity=Decimal('1'),
            unit_price=amount,
            invoice=invoice
        )
        
        # Manually call update_totals to ensure invoice total_amount is calculated
        Invoice.objects.update_totals(invoice)
        
        # Refresh invoice from DB to get updated total_amount
        invoice.refresh_from_db()
        return invoice

    def test_prevent_payment_on_draft_invoice(self):
        """Cannot add payment to DRAFT invoice."""
        invoice = self._create_invoice_with_amount(
            'DRAFT-001',
            Decimal('1000.00'),
            Invoice.Status.DRAFT
        )
        
        payment = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal('500.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            payment.full_clean()
        
        self.assertIn("Draft", str(context.exception))

    def test_prevent_payment_on_cancelled_invoice(self):
        """Cannot add payment to CANCELLED invoice."""
        invoice = self._create_invoice_with_amount(
            'CANC-001',
            Decimal('1000.00'),
            Invoice.Status.CANCELLED
        )
        
        payment = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal('500.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            payment.full_clean()
        
        self.assertIn("Cancelled", str(context.exception))

    def test_prevent_overpayment_single_payment(self):
        """Single payment cannot exceed invoice amount."""
        invoice = self._create_invoice_with_amount(
            'OVR-001',
            Decimal('1000.00'),
            Invoice.Status.PENDING
        )
        
        # Try to pay more than invoice amount
        payment = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal('1500.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            payment.full_clean()
        
        self.assertIn("exceed", str(context.exception).lower())

    def test_prevent_overpayment_cumulative(self):
        """Multiple payments cannot exceed invoice amount."""
        invoice = self._create_invoice_with_amount(
            'MULT-001',
            Decimal('1000.00'),
            Invoice.Status.PENDING
        )
        
        # Create first payment (valid)
        payment1 = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal('600.00')
        )
        
        # Try to add second payment that would exceed total
        payment2 = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal('500.00')  # Total would be R 1,100 > R 1,000
        )
        
        with self.assertRaises(ValidationError) as context:
            payment2.full_clean()
        
        self.assertIn("exceed", str(context.exception).lower())

    def test_allow_partial_payments(self):
        """Multiple partial payments should work up to invoice total."""
        invoice = self._create_invoice_with_amount(
            'PART-001',
            Decimal('1000.00'),
            Invoice.Status.PENDING
        )
        
        # First payment
        payment1 = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal('300.00')
        )
        self.assertEqual(invoice.total_paid, Decimal('300.00'))
        
        # Second payment
        payment2 = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal('400.00')
        )
        
        # Refresh to get updated total_paid
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_paid, Decimal('700.00'))
        
        # Third payment (fills the rest)
        payment3 = Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal('300.00')
        )
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_paid, Decimal('1000.00'))

    def test_prevent_negative_payment(self):
        """Cannot create negative payment."""
        invoice = self._create_invoice_with_amount(
            'NEG-001',
            Decimal('1000.00'),
            Invoice.Status.PENDING
        )
        
        payment = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal('-100.00')
        )
        
        with self.assertRaises(ValidationError):
            payment.full_clean()

    def test_prevent_negative_credit_applied(self):
        """Cannot apply negative credit."""
        invoice = self._create_invoice_with_amount(
            'NEGCRED-001',
            Decimal('1000.00'),
            Invoice.Status.PENDING
        )
        
        payment = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal('100.00'),
            credit_applied=Decimal('-50.00')
        )
        
        with self.assertRaises(ValidationError):
            payment.full_clean()

    def test_allow_zero_payment_with_credit(self):
        """Should allow $0 cash payment with credit applied."""
        invoice = self._create_invoice_with_amount(
            'CREDITONLY-001',
            Decimal('1000.00'),
            Invoice.Status.PENDING
        )
        
        # Credit-only payment (no cash, just credit applied)
        payment = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal('0.00'),
            credit_applied=Decimal('500.00')
        )
        
        # Should pass validation
        payment.full_clean()  # Should not raise
        payment.save()
        
        self.assertEqual(payment.amount, Decimal('0.00'))
        self.assertEqual(payment.credit_applied, Decimal('500.00'))


class InvoiceDataIntegrityTest(TestCase):
    """Test that invoice data integrity is maintained."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser3',
            email='test3@example.com',
            password='testpass123'
        )
        
        self.client = Client.objects.create(
            user=self.user,
            name='Test Client 3',
            email='client3@example.com'
        )

    def _create_invoice_with_amount(self, number, amount, status, due_date=None):
        """Helper to create invoice with items that total to the specified amount."""
        if due_date is None:
            due_date = timezone.now().date() + timedelta(days=14)
        
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            number=number,
            due_date=due_date,
            status=status
        )
        
        # Create an item linked to invoice with quantity * unit_price = amount
        # Use quantity=1 and unit_price=amount for simplicity
        Item.objects.create(
            user=self.user,
            client=self.client,
            description=f"Test item for {number}",
            quantity=Decimal('1'),
            unit_price=amount,
            invoice=invoice
        )
        
        # Manually call update_totals to ensure invoice total_amount is calculated
        Invoice.objects.update_totals(invoice)
        
        # Refresh invoice from DB to get updated total_amount
        invoice.refresh_from_db()
        return invoice

    def test_cancellation_reason_tracked(self):
        """Cancellation reason should be tracked and appear in credit note."""
        invoice = self._create_invoice_with_amount(
            'TRACK-001',
            Decimal('1000.00'),
            Invoice.Status.PAID
        )
        
        # Add payment
        Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal('1000.00')
        )
        
        # Cancel with reason
        reason = "Duplicate invoice issued by mistake"
        invoice.status = Invoice.Status.CANCELLED
        invoice.cancellation_reason = reason
        invoice.save()
        
        # Check credit note includes reason
        credit = CreditNote.objects.get(invoice=invoice)
        self.assertIn(reason, credit.description)

    def test_credit_note_reference_generated(self):
        """Credit note should have generated reference."""
        invoice = self._create_invoice_with_amount(
            'INV-2026-001',
            Decimal('1000.00'),
            Invoice.Status.PAID
        )
        
        Payment.objects.create(
            user=self.user,
            invoice=invoice,
            amount=Decimal('1000.00')
        )
        
        invoice.status = Invoice.Status.CANCELLED
        invoice.save()
        
        credit = CreditNote.objects.get(invoice=invoice)
        self.assertEqual(credit.reference, "CN-INV-2026-001")
