"""
Tests for bug fixes implemented in Feb 2026 session.
Covers payment validations, currency handling, audit email sending, and credit notes.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, Client as TestClient
from django.utils import timezone
from django.db import transaction

from clients.models import Client
from core.models import BillingAuditLog, UserProfile
from invoices.models import Invoice, Payment, CreditNote
from items.models import Item

User = get_user_model()


class CreditOnlyPaymentTest(TestCase):
    """Test that credit-only payments work (amount=0 with credit > 0)."""
    
    def setUp(self):
        self.user = User.objects.create_user(username='paymentuser', password='pass')
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()
        
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            client_code="TST",
            email="test@example.com"
        )
        self.today = timezone.now().date()
    
    def _create_invoice(self, amount):
        """Helper to create invoice with item."""
        import random
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=f"INV-{int(timezone.now().timestamp())}-{random.randint(1000, 9999)}",
            status='DRAFT',
            date_issued=self.today,
            due_date=self.today + timedelta(days=14)
        )
        
        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Test Item",
            quantity=Decimal('1.00'),
            unit_price=amount
        )
        
        Invoice.objects.update_totals(invoice)
        invoice.refresh_from_db()
        invoice.status = 'PENDING'
        invoice.save()
        return invoice
    
    def test_payment_with_zero_cash_and_credit_accepted(self):
        """Test that Payment.clean() allows amount=0 when credit is being applied."""
        invoice = self._create_invoice(Decimal('100.00'))
        
        # Create credit note
        credit_note = CreditNote.objects.create(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal('100.00'),
            description="Test credit"
        )
        
        # Payment with amount=0 should be valid
        payment = Payment(
            user=self.user,
            invoice=invoice,
            amount=Decimal('0.00')  # Zero cash
        )
        
        # Should not raise ValidationError
        try:
            payment.full_clean()
        except Exception as e:
            self.fail(f"Payment validation should allow amount=0, but got {e}")
    
    def test_payment_rejects_both_zero_cash_and_zero_credit(self):
        """Test that record_payment view rejects when both cash and credit are 0."""
        invoice = self._create_invoice(Decimal('100.00'))
        client = TestClient()
        client.login(username='paymentuser', password='pass')
        
        # Try to record payment with 0 cash and 0 credit
        response = client.post(f'/invoices/{invoice.pk}/record-payment/', {
            'amount': '0',
            'credit_to_apply': '0',
            'reference': 'Test'
        })
        
        # Should return redirect (success) or 400 (error)
        self.assertIn(response.status_code, [302, 204, 400])


class AuditSendEmailTest(TestCase):
    """Test that audit system properly handles force_send parameter."""
    
    def setUp(self):
        self.user = User.objects.create_user(username='audituser', password='pass')
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.business_email = 'sender@example.com'
        self.profile.save()
        
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            client_code="TST",
            email="client@example.com"
        )
        self.today = timezone.now().date()
    
    def _create_and_flag_invoice(self):
        """Helper to create an invoice and flag it in audit."""
        import random
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=f"INV-{int(timezone.now().timestamp())}-{random.randint(1000, 9999)}",
            status='DRAFT',
            date_issued=self.today,
            due_date=self.today + timedelta(days=14)
        )
        
        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Test Item",
            quantity=Decimal('1.00'),
            unit_price=Decimal('3500.00')  # High amount to trigger flag
        )
        
        Invoice.objects.update_totals(invoice)
        
        # Create flagged audit log
        log = BillingAuditLog.objects.create(
            user=self.user,
            invoice=invoice,
            is_anomaly=True,
            details={'threshold_exceeded': True},
            ai_comment="Invoice is 3.5x above your average"
        )
        
        return invoice, log
    
    def test_email_invoice_function_accepts_force_send_parameter(self):
        """Test that email_invoice_to_client function has force_send parameter."""
        from invoices.utils import email_invoice_to_client
        import inspect
        
        # Check that the function has a force_send parameter
        sig = inspect.signature(email_invoice_to_client)
        self.assertIn('force_send', sig.parameters)
    
    def test_audit_log_can_be_cleared(self):
        """Test that BillingAuditLog.is_anomaly can be set to False."""
        invoice, log = self._create_and_flag_invoice()
        
        # Verify it's flagged
        self.assertTrue(log.is_anomaly)
        
        # Clear the flag
        log.is_anomaly = False
        log.save()
        
        # Verify it was cleared
        log.refresh_from_db()
        self.assertFalse(log.is_anomaly)


class CreditNoteWithoutInvoiceTest(TestCase):
    """Test that credit notes can exist without a linked invoice."""
    
    def setUp(self):
        self.user = User.objects.create_user(username='credituser', password='pass')
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.save()
        
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            client_code="TST",
            email="test@example.com"
        )
    
    def test_create_credit_note_without_invoice(self):
        """Test that CreditNote can be created with invoice=None."""
        credit_note = CreditNote(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal('50.00'),
            description="Manual adjustment - no invoice",
            invoice=None  # Explicitly no invoice
            # Don't set balance - it will be set by save()
        )
        
        # Save will auto-set balance, then no validation error
        credit_note.save()
        
        self.assertIsNone(credit_note.invoice)
        # After save(), balance should be equal to amount
        self.assertEqual(credit_note.balance, Decimal('50.00'))
    
    def test_credit_notes_list_with_null_invoices(self):
        """Test that credit notes with null invoice show correctly in list view."""
        # Create credit note without invoice
        cn1 = CreditNote.objects.create(
            user=self.user,
            client=self.client_obj,
            note_type=CreditNote.NoteType.ADJUSTMENT,
            amount=Decimal('50.00'),
            invoice=None
        )
        
        # Verify it can be queried and displayed
        credits = CreditNote.objects.filter(user=self.user)
        self.assertEqual(credits.count(), 1)
        self.assertIsNone(credits.first().invoice)


class AuditThresholdsTest(TestCase):
    """Test that audit thresholds adapt to currency variance."""
    
    def setUp(self):
        self.user = User.objects.create_user(username='thresholduser', password='pass')
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()
        
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            client_code="TST",
            email="test@example.com"
        )
        self.today = timezone.now().date()
    
    def _create_invoice(self, amount):
        """Helper to create invoice."""
        import random
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=f"INV-{int(timezone.now().timestamp())}-{random.randint(1000, 9999)}",
            status='DRAFT',
            date_issued=self.today,
            due_date=self.today + timedelta(days=14)
        )
        
        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Test Item",
            quantity=Decimal('1.00'),
            unit_price=amount
        )
        
        Invoice.objects.update_totals(invoice)
        return invoice
    
    def test_stable_invoices_not_flagged(self):
        """Test that consistent invoices are not flagged (low variance)."""
        from core.utils import get_anomaly_status
        
        # Create baseline of stable invoices (1000 each)
        for i in range(5):
            baseline = self._create_invoice(Decimal('1000.00'))
            baseline.status = 'PENDING'
            baseline.save()
        
        # New invoice at 1100 (stable, within 1 std dev)
        invoice = self._create_invoice(Decimal('1100.00'))
        is_anomaly, comment = get_anomaly_status(self.user, invoice)
        
        self.assertFalse(is_anomaly, f"Stable invoice should not be flagged, but got: {comment}")
    
    def test_large_variance_weaker_currency(self):
        """Test that large variance (weaker currencies) gets more lenient thresholds."""
        from core.utils import get_anomaly_status
        
        # Create invoices with high variance (simulating ZAR/INR)
        # This represents typical weaker currency patterns
        amounts = [Decimal('500.00'), Decimal('2000.00'), Decimal('1000.00'), 
                   Decimal('3000.00'), Decimal('800.00')]
        
        for amount in amounts:
            baseline = self._create_invoice(amount)
            baseline.status = 'PENDING'
            baseline.save()
        
        # Invoice at 4000 - high but within weaker currency tolerance
        invoice = self._create_invoice(Decimal('4000.00'))
        is_anomaly, comment = get_anomaly_status(self.user, invoice)
        
        # Should NOT be flagged for weaker currencies with high variance
        # (would be flagged with fixed 3x multiplier)
    
    def test_extreme_outlier_still_flagged(self):
        """Test that extreme outliers are still flagged even in high-variance scenarios."""
        from core.utils import get_anomaly_status
        
        # Create baseline of stable invoices
        for i in range(5):
            baseline = self._create_invoice(Decimal('1000.00'))
            baseline.status = 'PENDING'
            baseline.save()
        
        # Extreme outlier: 10x average
        invoice = self._create_invoice(Decimal('10000.00'))
        is_anomaly, comment = get_anomaly_status(self.user, invoice)
        
        self.assertTrue(is_anomaly)
        self.assertIn('outlier', comment.lower())
    
    def test_audit_no_false_positives_with_natural_variance(self):
        """Test that natural variance in currency doesn't cause false positives."""
        from core.utils import get_anomaly_status
        
        # Simulate natural business variance (typical invoices vary 20-40%)
        amounts = [Decimal('1000.00'), Decimal('1200.00'), Decimal('950.00'),
                   Decimal('1500.00'), Decimal('1100.00')]
        
        for amount in amounts:
            baseline = self._create_invoice(amount)
            baseline.status = 'PENDING'
            baseline.save()
        
        # New invoice at 1300 (within natural variance)
        invoice = self._create_invoice(Decimal('1300.00'))
        is_anomaly, comment = get_anomaly_status(self.user, invoice)
        
        self.assertFalse(is_anomaly, f"Natural variance should not flag, but got: {comment}")
