from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from clients.models import Client
from invoices.models import Invoice, Payment
from items.models import Item
from core.middleware import set_current_user

User = get_user_model()

class PaymentMasterTest(TestCase):
    def setUp(self):
        # 1. Create Users
        self.user_a = User.objects.create_user(username="tenant_a", email="a@diode.co.za", password="pin")
        self.user_b = User.objects.create_user(username="tenant_b", email="b@diode.co.za", password="pin")
        
        # 2. Setup Profile
        for user in [self.user_a, self.user_b]:
            profile = user.profile
            profile.initial_setup_complete = True
            profile.save()

        # 3. Create Client for User A
        self.client_a = Client.objects.create(user=self.user_a, name="Client A", client_code="CLA")

        # 4. Create Invoice
        self.invoice_a = Invoice.objects.create(
            user=self.user_a,
            client=self.client_a,
            number="INV-A-001",
            status="PENDING",
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14),
        )

        # 5. Create Item - NOW WITH CLIENT (to fix IntegrityError)
        Item.objects.create(
            user=self.user_a, 
            invoice=self.invoice_a,
            client=self.client_a, # <--- THIS IS THE FIX
            quantity=Decimal("1.00"), 
            unit_price=Decimal("500.00")
        )
        
        # Sync the totals so balance_due is R500.00
        self.invoice_a.sync_totals()
        self.invoice_a.save()
        self.invoice_a.refresh_from_db()


    def test_tenant_isolation_prevents_cross_payment(self):
        """
        Verify that User B cannot pay User A's invoice, 
        even if the invoice has a valid balance.
        """
        set_current_user(self.user_b)
        try:
            # This should trigger PermissionDenied based on the User/Tenant mismatch
            with self.assertRaises(PermissionDenied):
                Payment.objects.create(
                    user=self.user_b,
                    invoice=self.invoice_a,
                    amount=Decimal("100.00"),
                    reference="Illicit Payment"
                )
        finally:
            set_current_user(None)

    def test_valid_payment_flow(self):
        """
        Verify that User A can pay their own invoice and balance updates.
        """
        set_current_user(self.user_a)
        try:
            self.assertEqual(self.invoice_a.balance_due, Decimal("500.00"))
            
            Payment.objects.create(
                user=self.user_a,
                invoice=self.invoice_a,
                amount=Decimal("200.00"),
                reference="Valid Partial"
            )
            
            self.invoice_a.refresh_from_db()
            self.assertEqual(self.invoice_a.balance_due, Decimal("300.00"))
        finally:
            set_current_user(None)

    def test_overpayment_rejected(self):
        """Verify the R 0.00 / Overpayment guard still works."""
        set_current_user(self.user_a)
        try:
            with self.assertRaises(ValidationError):
                payment = Payment(
                    user=self.user_a,
                    invoice=self.invoice_a,
                    amount=Decimal("600.00") # Exceeds the R 500.00 item
                )
                payment.full_clean()
        finally:
            set_current_user(None)