from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice, Payment
from items.models import Item

User = get_user_model()


class PaymentValidationTest(TestCase):
    """Test that payment validation prevents overpayments."""
    
    def setUp(self):
        """Set up test user and invoice."""
        self.user = User.objects.create_user(username='payment_tester', password='pass')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()
        
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Payment Test Client",
            client_code="PAY"
        )
        
        self.invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="INV-PAY-TEST-01",  # Added explicit number to 
                                       #satisfy unique constraint
            status='DRAFT',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14)
        )
        
        # Add items to make total R500
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=self.invoice,
            description="Test Item",
            quantity=Decimal('5.00'),
            unit_price=Decimal('100.00')
        )
        
        # Update totals using the manager
        Invoice.objects.update_totals(self.invoice)
        self.invoice.refresh_from_db()

    def test_payment_under_balance_succeeds(self):
        """Verify that payments under balance due are accepted."""
        self.assertEqual(self.invoice.balance_due, Decimal('500.00'))
        
        Payment.objects.create(
            user=self.user,      # Added user
            invoice=self.invoice,
            amount=Decimal('200.00'),
            reference='Test Payment'
        )
        
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('300.00'))
        print("✓ Partial payment (R200 of R500) accepted")

    def test_payment_equal_to_balance_succeeds(self):
        """Verify that payments equal to balance due are accepted."""
        Payment.objects.create(
            user=self.user,      # Added user
            invoice=self.invoice,
            amount=Decimal('500.00'),
            reference='Full Payment'
        )
        
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('0.00'))
        self.assertEqual(self.invoice.status, 'PAID')
        print("✓ Full payment (R500) accepted and invoice marked paid")

    def test_payment_exceeds_balance_rejected(self):
        """Verify that payments exceeding balance due are rejected."""
        with self.assertRaises(ValidationError) as context:
            payment = Payment(
                user=self.user,  # Added user
                invoice=self.invoice,
                amount=Decimal('600.00'),
                reference='Overpayment'
            )
            payment.full_clean()
        
        self.assertIn('cannot exceed', str(context.exception))
        print("✓ Overpayment (R600 of R500) rejected with validation error")

    def test_zero_payment_rejected(self):
        """Verify that zero or negative payments are rejected."""
        with self.assertRaises(ValidationError) as context:
            payment = Payment(
                user=self.user,  # Added user
                invoice=self.invoice,
                amount=Decimal('0.00'),
                reference='Zero Payment'
            )
            payment.full_clean()
        
        self.assertIn('greater than zero', str(context.exception))
        print("✓ Zero payment rejected")

    def test_multiple_partial_payments(self):
        """Verify that multiple partial payments accumulate correctly."""
        # First payment
        Payment.objects.create(
            user=self.user,      # Added user
            invoice=self.invoice,
            amount=Decimal('200.00'),
            reference='Payment 1'
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('300.00'))
        
        # Second payment
        Payment.objects.create(
            user=self.user,      # Added user
            invoice=self.invoice,
            amount=Decimal('150.00'),
            reference='Payment 2'
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('150.00'))
        self.assertNotEqual(self.invoice.status, 'PAID')
        
        # Third payment (final)
        Payment.objects.create(
            user=self.user,      # Added user
            invoice=self.invoice,
            amount=Decimal('150.00'),
            reference='Payment 3'
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('0.00'))
        self.assertEqual(self.invoice.status, 'PAID')
        print("✓ Multiple payments (R200 + R150 + R150 = R500) handled correctly")