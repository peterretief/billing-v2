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
        self.user = User.objects.create_user(username='tester', password='pass')
        
        # Explicitly create the profile for the test user
        self.profile, created = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.company_name = "Test Company"
        self.profile.save()
        
        self.client = Client.objects.create(
            user=self.user, 
            name="Test Client", 
            client_code="TST"
        )

    def test_standard_timesheet_billing(self):
        """Verify that standard InvoiceItems calculate correctly."""
        today = timezone.now().date()
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            status='DRAFT',
            date_issued=today,
            due_date=today + timedelta(days=14)
        )
        
        # Add a standard item (e.g., 5 hours @ 100)
        Item.objects.create(
            user=self.user,
            client=self.client,
            invoice=invoice,
            description="Development Work",
            quantity=Decimal('5.00'),
            unit_price=Decimal('100.00')
        )
        
        invoice.save()
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal('500.00'))
        print(f"Standard Billing Success: \
              {invoice.number} total is {invoice.total_amount}")
