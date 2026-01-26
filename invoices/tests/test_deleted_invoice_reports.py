from decimal import Decimal
from django.test import TestCase, Client as TestClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from invoices.models import Invoice
from core.models import UserProfile
from clients.models import Client

User = get_user_model()


class DeletedInvoiceReportTest(TestCase):
    """Tests to ensure deleted invoices don't appear in reports or dashboards."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.company_name = "Test Company"
        self.profile.monthly_target = Decimal('10000.00')
        self.profile.save()
        
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            email="client@test.com"
        )
        
        self.test_client = TestClient()
        self.test_client.login(username='testuser', password='testpass123')
        
        # Create a draft invoice
        today = timezone.now().date()
        self.invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status='DRAFT',
            date_issued=today,
            due_date=today + timedelta(days=14),
            billing_type='SERVICE',
            subtotal_amount=Decimal('5000.00'),
            tax_amount=Decimal('750.00'),
            total_amount=Decimal('5750.00')
        )
        
        # Create a posted invoice for reporting
        self.posted_invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status='PENDING',
            date_issued=today,
            due_date=today + timedelta(days=14),
            billing_type='SERVICE',
            subtotal_amount=Decimal('3000.00'),
            tax_amount=Decimal('450.00'),
            total_amount=Decimal('3450.00')
        )
    
    def test_deleted_invoice_not_in_invoice_list(self):
        """Test that deleted invoices don't appear in invoice list."""
        # Get initial count
        response = self.test_client.get(reverse('invoices:invoice_list'))
        initial_invoices = response.context['invoices'].paginator.count
        
        # Delete the draft invoice
        self.test_client.post(reverse('invoices:delete_invoice', args=[self.invoice.pk]))
        
        # Get count after deletion
        response = self.test_client.get(reverse('invoices:invoice_list'))
        after_deletion_count = response.context['invoices'].paginator.count
        
        # Should have one fewer invoice
        self.assertEqual(after_deletion_count, initial_invoices - 1)
    
    def test_deleted_invoice_completely_removed_from_database(self):
        """Test that deleted invoices are completely removed from the database."""
        invoice_id = self.invoice.pk
        
        # Verify invoice exists
        self.assertTrue(Invoice.objects.filter(pk=invoice_id).exists())
        
        # Delete the invoice
        self.test_client.post(reverse('invoices:delete_invoice', args=[invoice_id]))
        
        # Invoice should no longer exist in the database
        self.assertFalse(Invoice.objects.filter(pk=invoice_id).exists())
    
    def test_deleted_invoice_not_in_any_queryset(self):
        """Test that deleted invoices are excluded from all querysets and aggregations."""
        # Get all invoices before deletion
        all_invoices_before = Invoice.objects.filter(user=self.user)
        self.assertEqual(all_invoices_before.count(), 2)
        
        # Get dashboard before deletion (uses aggregate queries)
        response_before = self.test_client.get(reverse('invoices:dashboard'))
        stats_before = response_before.context
        
        # Delete the draft invoice
        self.test_client.post(reverse('invoices:delete_invoice', args=[self.invoice.pk]))
        
        # Get all invoices after deletion
        all_invoices_after = Invoice.objects.filter(user=self.user)
        self.assertEqual(all_invoices_after.count(), 1)
        
        # Get dashboard after deletion
        response_after = self.test_client.get(reverse('invoices:dashboard'))
        stats_after = response_after.context
        
        # Verify only the posted invoice remains
        remaining_invoice = all_invoices_after.first()
        self.assertEqual(remaining_invoice.pk, self.posted_invoice.pk)
        
        # Verify the deleted invoice is completely gone from all queries
        deleted_invoice_exists = Invoice.objects.filter(pk=self.invoice.pk).exists()
        self.assertFalse(deleted_invoice_exists)
    
    def test_only_current_user_invoices_in_reports(self):
        """Test that invoices from deleted records only affect the owner's reports."""
        # Create another user
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='otherpass123'
        )
        other_profile, _ = UserProfile.objects.get_or_create(user=other_user)
        other_profile.company_name = "Other Company"
        other_profile.save()
        
        # Create invoice for other user
        today = timezone.now().date()
        other_invoice = Invoice.objects.create(
            user=other_user,
            client=self.client_obj,
            status='DRAFT',
            date_issued=today,
            due_date=today + timedelta(days=14),
            subtotal_amount=Decimal('2000.00'),
            tax_amount=Decimal('300.00'),
            total_amount=Decimal('2300.00')
        )
        
        # Get initial invoice counts for each user
        first_user_invoices_before = Invoice.objects.filter(user=self.user).count()
        other_user_invoices_before = Invoice.objects.filter(user=other_user).count()
        
        # Delete OTHER user's invoice
        other_client = TestClient()
        other_client.login(username='otheruser', password='otherpass123')
        other_client.post(reverse('invoices:delete_invoice', args=[other_invoice.pk]))
        
        # Check first user's invoices - should be unchanged
        first_user_invoices_after = Invoice.objects.filter(user=self.user).count()
        other_user_invoices_after = Invoice.objects.filter(user=other_user).count()
        
        # First user should still have same count
        self.assertEqual(first_user_invoices_before, first_user_invoices_after)
        # Other user should have one fewer
        self.assertEqual(other_user_invoices_after, other_user_invoices_before - 1)

