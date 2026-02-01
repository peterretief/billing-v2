from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice
from items.models import Item
from timesheets.models import TimesheetEntry

User = get_user_model()


class InvoiceDeleteTest(TestCase):
    """Tests for invoice deletion, ensuring no orphaned timesheets or items."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.company_name = "Test Company"
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
            billing_type='SERVICE'
        )
    
    def test_delete_draft_invoice_view_requires_login(self):
        """Test that delete view requires authentication."""
        anon_client = TestClient()
        response = anon_client.get(reverse('invoices:delete_invoice', args=[self.invoice.pk]))
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
    
    def test_delete_draft_invoice_get_shows_confirmation(self):
        """Test that GET request shows confirmation page."""
        response = self.test_client.get(
            reverse('invoices:delete_invoice', args=[self.invoice.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invoices/invoice_confirm_delete.html')
        self.assertContains(response, self.invoice.number or str(self.invoice.id))
    
    def test_delete_draft_invoice_post_succeeds(self):
        """Test that POST request deletes the draft invoice."""
        invoice_id = self.invoice.pk
        response = self.test_client.post(
            reverse('invoices:delete_invoice', args=[invoice_id])
        )
        
        # Should redirect to invoice list
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('invoices:invoice_list'))
        
        # Invoice should no longer exist
        self.assertFalse(Invoice.objects.filter(pk=invoice_id).exists())
    
    def test_delete_non_draft_invoice_fails(self):
        """Test that only DRAFT invoices can be deleted."""
        # Change status to PENDING
        self.invoice.status = 'PENDING'
        self.invoice.save()
        
        response = self.test_client.post(
            reverse('invoices:delete_invoice', args=[self.invoice.pk])
        )
        
        # Should redirect back to invoice detail
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('invoices:invoice_detail', args=[self.invoice.pk])
        )
        
        # Invoice should still exist
        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk).exists())
    
    def test_delete_invoice_preserves_linked_timesheets(self):
        """Test that linked timesheets are preserved (not deleted) when invoice is deleted."""
        # Create a timesheet linked to this invoice
        timesheet = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            date=timezone.now().date(),
            description="Test work",
            hours=Decimal('8.00'),
            hourly_rate=Decimal('100.00'),
            is_billed=False,
            invoice=self.invoice  # Link it to the invoice
        )
        
        timesheet_id = timesheet.pk
        invoice_id = self.invoice.pk
        
        # Delete the invoice
        self.test_client.post(reverse('invoices:delete_invoice', args=[invoice_id]))
        
        # Timesheet should still exist
        self.assertTrue(TimesheetEntry.objects.filter(pk=timesheet_id).exists())
        
        # But it should no longer be linked to the invoice
        updated_timesheet = TimesheetEntry.objects.get(pk=timesheet_id)
        self.assertIsNone(updated_timesheet.invoice)
    
    def test_delete_invoice_preserves_linked_items(self):
        """Test that linked items are preserved (not deleted) when invoice is deleted."""
        # Create an item linked to this invoice
        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Test item",
            quantity=Decimal('1.00'),
            unit_price=Decimal('100.00'),
            is_billed=False,
            invoice=self.invoice  # Link it to the invoice
        )
        
        item_id = item.pk
        invoice_id = self.invoice.pk
        
        # Delete the invoice
        self.test_client.post(reverse('invoices:delete_invoice', args=[invoice_id]))
        
        # Item should still exist
        self.assertTrue(Item.objects.filter(pk=item_id).exists())
        
        # But it should no longer be linked to the invoice
        updated_item = Item.objects.get(pk=item_id)
        self.assertIsNone(updated_item.invoice)
    
    def test_delete_invoice_with_multiple_items_and_timesheets(self):
        """Test deletion with multiple linked items and timesheets."""
        # Create multiple timesheets
        timesheets = [
            TimesheetEntry.objects.create(
                user=self.user,
                client=self.client_obj,
                date=timezone.now().date(),
                description=f"Work {i}",
                hours=Decimal('8.00'),
                hourly_rate=Decimal('100.00'),
                invoice=self.invoice
            )
            for i in range(3)
        ]
        
        # Create multiple items
        items = [
            Item.objects.create(
                user=self.user,
                client=self.client_obj,
                description=f"Item {i}",
                quantity=Decimal('1.00'),
                unit_price=Decimal('50.00'),
                invoice=self.invoice
            )
            for i in range(2)
        ]
        
        timesheet_ids = [ts.pk for ts in timesheets]
        item_ids = [item.pk for item in items]
        invoice_id = self.invoice.pk
        
        # Delete the invoice
        self.test_client.post(reverse('invoices:delete_invoice', args=[invoice_id]))
        
        # Invoice should be deleted
        self.assertFalse(Invoice.objects.filter(pk=invoice_id).exists())
        
        # All timesheets should still exist but unlinked
        for ts_id in timesheet_ids:
            ts = TimesheetEntry.objects.get(pk=ts_id)
            self.assertIsNone(ts.invoice)
        
        # All items should still exist but unlinked
        for item_id in item_ids:
            item = Item.objects.get(pk=item_id)
            self.assertIsNone(item.invoice)
    
    def test_delete_invoice_user_isolation(self):
        """Test that users can only delete their own invoices."""
        # Create another user
        User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='pass123'
        )
        
        # Try to delete invoice as different user (will fail auth check)
        other_client = TestClient()
        other_client.login(username='otheruser', password='pass123')
        
        # This should result in a 404 because the invoice belongs to a different user
        response = other_client.post(
            reverse('invoices:delete_invoice', args=[self.invoice.pk])
        )
        
        # The view should not find the invoice (404 or similar)
        # In Django, get_object_or_404 with filter will raise 404
        self.assertEqual(response.status_code, 404)
        
        # Original invoice should still exist
        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk).exists())
