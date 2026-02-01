import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice

User = get_user_model()

class DeletedInvoiceReportTest(TestCase):
    """Test that deleted invoices do not appear in reports or querysets."""

    def setUp(self):
        """Set up unique data for every test run."""
        unique_id = uuid.uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f'user_{unique_id}',
            email=f'test_{unique_id}@example.com',
            password='password123'
        )
        
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.save()

        self.client_obj = Client.objects.create(
            user=self.user,
            name="Report Test Client"
        )

        self.invoice_number = f"INV-{unique_id.upper()}"
        today = timezone.now().date()

        self.posted_invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=self.invoice_number,
            status='POSTED',
            date_issued=today,
            due_date=today + timedelta(days=14),  # <--- FIXED: Added due_date
            total_amount=Decimal('1000.00')
        )

    def test_deleted_invoice_completely_removed_from_database(self):
        """Verify the invoice is actually gone after deletion."""
        invoice_id = self.posted_invoice.pk
        self.posted_invoice.delete()
        self.assertFalse(Invoice.objects.filter(pk=invoice_id).exists())

    def test_deleted_invoice_not_in_any_queryset(self):
        """Ensure aggregations ignore deleted records."""
        self.posted_invoice.delete()
        count = Invoice.objects.filter(user=self.user).count()
        self.assertEqual(count, 0)

    def test_only_current_user_invoices_in_reports(self):
        """Verify multi-tenancy holds during reporting."""
        other_id = uuid.uuid4().hex[:8]
        other_user = User.objects.create_user(
            username=f'other_{other_id}',
            email=f'other_{other_id}@example.com',
            password='password123'
        )
        today = timezone.now().date()
        
        Invoice.objects.create(
            user=other_user,
            client=Client.objects.create(user=other_user, name="Other"),
            number=f"INV-OTHER-{other_id}",
            status='POSTED',
            date_issued=today,
            due_date=today + timedelta(days=14),  # <--- FIXED: Added due_date
        )
        
        self.assertEqual(Invoice.objects.filter(user=self.user).count(), 1)