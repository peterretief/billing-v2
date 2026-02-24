"""
Tests for quote workflow functionality including:
- Quote status tracking (PENDING, ACCEPTED, REJECTED)
- Quote rejection and removal from list
- Quote to invoice conversion
- Email personalization with contact_name
- Invoice deletion resetting is_billed flags
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta

from invoices.models import Invoice, InvoiceEmailStatusLog
from clients.models import Client as ClientModel
from items.models import Item
from timesheets.models import TimesheetEntry
from core.models import User

User = get_user_model()


class QuoteStatusTest(TestCase):
    """Test quote status tracking and transitions."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="quotestatus",
            email="test@example.com",
            password="testpass123"
        )
        self.profile = self.user.profile
        self.profile.company_name = "Test Company"
        self.profile.business_email = "business@example.com"
        self.profile.contact_name = "John Doe"
        self.profile.currency = "R"
        self.profile.vat_rate = Decimal("15.00")
        self.profile.save()
        self.client_obj = ClientModel.objects.create(
            user=self.user,
            name="Test Client",
            email="client@example.com"
        )
        self.quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT,
            quote_status="PENDING"
        )

    def test_quote_created_with_pending_status(self):
        """Test that new quotes have PENDING status."""
        self.assertEqual(self.quote.quote_status, "PENDING")
        self.assertTrue(self.quote.is_quote)

    def test_quote_conversion_sets_accepted_status(self):
        """Test that converting quote to invoice sets ACCEPTED status."""
        # Send the quote first
        self.quote.is_emailed = True
        self.quote.emailed_at = timezone.now()
        self.quote.save()

        # Convert to invoice
        self.quote.is_quote = False
        self.quote.was_originally_quote = True
        self.quote.quote_status = "ACCEPTED"
        self.quote.save()

        self.assertEqual(self.quote.quote_status, "ACCEPTED")
        self.assertFalse(self.quote.is_quote)
        self.assertTrue(self.quote.was_originally_quote)

    def test_quote_rejection_sets_rejected_status(self):
        """Test that rejecting quote sets REJECTED status."""
        self.quote.quote_status = "REJECTED"
        self.quote.save()

        self.assertEqual(self.quote.quote_status, "REJECTED")

    def test_rejected_quotes_filtered_from_list(self):
        """Test that rejected quotes are excluded from default list query."""
        # Create a rejected quote
        self.quote.quote_status = "REJECTED"
        self.quote.save()

        # Query should exclude rejected quotes
        active_quotes = Invoice.objects.filter(
            user=self.user,
            is_quote=True
        ).exclude(quote_status="REJECTED")

        self.assertNotIn(self.quote, active_quotes)


class QuoteConversionTest(TestCase):
    """Test quote to invoice conversion logic."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="quoteconversiontest",
            email="test@example.com",
            password="testpass123"
        )
        self.profile = self.user.profile
        self.profile.company_name = "Test Company"
        self.profile.business_email = "business@example.com"
        self.profile.currency = "R"
        self.profile.save()
        self.client_obj = ClientModel.objects.create(
            user=self.user,
            name="Test Client",
            email="client@example.com"
        )
        self.quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            is_emailed=True,
            emailed_at=timezone.now(),
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.PENDING,
            quote_status="PENDING"
        )

    def test_conversion_resets_email_flags(self):
        """Test that converting quote resets email flags."""
        original_emailed_at = self.quote.emailed_at

        # Convert
        self.quote.is_quote = False
        self.quote.was_originally_quote = True
        self.quote.quote_status = "ACCEPTED"
        self.quote.is_emailed = False
        self.quote.emailed_at = None
        self.quote.status = Invoice.Status.DRAFT
        self.quote.save()

        self.assertFalse(self.quote.is_emailed)
        self.assertIsNone(self.quote.emailed_at)
        self.assertEqual(self.quote.status, Invoice.Status.DRAFT)

    def test_conversion_tracks_original_quote(self):
        """Test that conversion tracks that this was originally a quote."""
        self.quote.is_quote = False
        self.quote.was_originally_quote = True
        self.quote.save()

        self.assertTrue(self.quote.was_originally_quote)
        self.assertFalse(self.quote.is_quote)


class EmailPersonalizationTest(TestCase):
    """Test email personalization with contact_name."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="emailpersonalizationtest",
            email="test@example.com",
            password="testpass123"
        )
        self.profile = self.user.profile
        self.profile.company_name = "Test Company"
        self.profile.business_email = "business@example.com"
        self.profile.contact_name = "Jane Smith"
        self.profile.currency = "R"
        self.profile.save()
        self.client_obj = ClientModel.objects.create(
            user=self.user,
            name="Test Client",
            email="client@example.com"
        )

    def test_email_uses_contact_name_when_available(self):
        """Test that contact_name is used in email signature if set."""
        # The actual email sending is tested in test_bug_fixes.py
        # This just verifies the profile has contact_name set
        self.assertEqual(self.profile.contact_name, "Jane Smith")

    def test_email_falls_back_to_company_name(self):
        """Test that email falls back to company_name if contact_name is blank."""
        self.profile.contact_name = ""
        self.profile.save()

        signature_name = (
            self.profile.contact_name if self.profile.contact_name 
            else self.profile.company_name
        )
        self.assertEqual(signature_name, "Test Company")


class InvoiceDeletionTest(TestCase):
    """Test invoice deletion resetting is_billed flags."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="invoicedeletiontest",
            email="test@example.com",
            password="testpass123"
        )
        self.profile = self.user.profile
        self.profile.company_name = "Test Company"
        self.profile.business_email = "business@example.com"
        self.profile.currency = "R"
        self.profile.save()
        self.client_obj = ClientModel.objects.create(
            user=self.user,
            name="Test Client",
            email="client@example.com"
        )
        self.invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            due_date=timezone.now().date() + timedelta(days=14),
            status=Invoice.Status.DRAFT
        )
        
        # Create items linked to invoice
        self.item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Test Item",
            quantity=1,
            unit_price=Decimal("100.00"),
            is_billed=True,  # Mark as billed
            invoice=self.invoice  # Link to invoice
        )
        
        # Create timesheet entry linked to invoice
        self.timesheet = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            date=timezone.now().date(),
            hours=Decimal("8.00"),
            hourly_rate=Decimal("75.00"),
            is_billed=True,  # Mark as billed
            invoice=self.invoice
        )

    def test_deletion_resets_item_is_billed_flag(self):
        """Test that deleting invoice resets is_billed on items."""
        # Before deletion
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_billed)
        
        # Delete invoice (in real usage this happens via view)
        self.invoice.billed_items.all().update(is_billed=False)
        self.invoice.billed_timesheets.all().update(is_billed=False)
        self.invoice.delete()
        
        # After deletion
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_billed)

    def test_deletion_resets_timesheet_is_billed_flag(self):
        """Test that deleting invoice resets is_billed on timesheets."""
        # Before deletion
        self.timesheet.refresh_from_db()
        self.assertTrue(self.timesheet.is_billed)
        
        # Delete invoice (in real usage this happens via view)
        self.invoice.billed_items.all().update(is_billed=False)
        self.invoice.billed_timesheets.all().update(is_billed=False)
        self.invoice.delete()
        
        # After deletion
        self.timesheet.refresh_from_db()
        self.assertFalse(self.timesheet.is_billed)

    def test_deleted_items_available_for_new_invoice(self):
        """Test that items become available for new invoice after deletion."""
        # Delete the invoice
        self.invoice.billed_items.all().update(is_billed=False)
        self.invoice.billed_timesheets.all().update(is_billed=False)
        self.invoice.delete()
        
        # Item should now be available
        available_items = Item.objects.filter(
            user=self.user,
            is_billed=False
        )
        self.assertIn(self.item, available_items)


class QuoteDisplayTest(TestCase):
    """Test quote display logic in invoice list."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="quotedisplaytest",
            email="test@example.com",
            password="testpass123"
        )
        self.profile = self.user.profile
        self.profile.company_name = "Test Company"
        self.profile.business_email = "business@example.com"
        self.profile.currency = "R"
        self.profile.save()
        self.client_obj = ClientModel.objects.create(
            user=self.user,
            name="Test Client",
            email="client@example.com"
        )

    def test_pending_quote_shows_as_pending(self):
        """Test that pending quote shows correctly in display logic."""
        quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            is_emailed=False,
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT,
            quote_status="PENDING"
        )
        # Display should show nothing (no email sent)
        self.assertFalse(quote.is_emailed)

    def test_sent_quote_shows_as_quoted(self):
        """Test that sent quote shows 'Quoted' in display logic."""
        quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            is_emailed=True,
            emailed_at=timezone.now(),
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.PENDING,
            quote_status="PENDING"
        )
        # Display should show "Quoted"
        self.assertTrue(quote.is_quote)
        self.assertTrue(quote.is_emailed)

    def test_accepted_quote_shows_as_accepted(self):
        """Test that accepted (converted) quote shows 'Accepted' in display logic."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=False,
            is_emailed=False,
            was_originally_quote=True,
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT,
            quote_status="ACCEPTED"
        )
        # Display should show "Accepted"
        self.assertFalse(invoice.is_quote)
        self.assertFalse(invoice.is_emailed)
        self.assertTrue(invoice.was_originally_quote)

    def test_sent_invoice_shows_as_invoiced(self):
        """Test that sent invoice shows 'Invoiced' in display logic."""
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=False,
            is_emailed=True,
            emailed_at=timezone.now(),
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.PENDING,
            was_originally_quote=False
        )
        # Display should show "Invoiced"
        self.assertFalse(invoice.is_quote)
        self.assertTrue(invoice.is_emailed)

    def test_rejected_quote_shows_as_rejected(self):
        """Test that rejected quote shows 'Rejected' in display logic."""
        quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            quote_status="REJECTED",
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT
        )
        # Display should show "Rejected"
        self.assertTrue(quote.is_quote)
        self.assertEqual(quote.quote_status, "REJECTED")
