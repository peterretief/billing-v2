"""
Tests for quote rejection functionality and workflow transitions.
"""

from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta

from invoices.models import Invoice
from clients.models import Client as ClientModel

User = get_user_model()


class QuoteRejectionDataTest(TestCase):
    """Test the data model changes for quote rejection."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="rejectquotetest",
            email="test@example.com",
            password="testpass123"
        )
        self.profile = self.user.profile
        self.profile.company_name = "Test Company"
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
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT,
            quote_status="PENDING"
        )

    def test_quote_can_be_set_to_rejected(self):
        """Test that quote_status can be set to REJECTED."""
        self.quote.quote_status = "REJECTED"
        self.quote.save()
        
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.quote_status, "REJECTED")

    def test_rejected_quote_can_be_filtered_out(self):
        """Test that rejected quotes can be easily filtered from queries."""
        self.quote.quote_status = "REJECTED"
        self.quote.save()
        
        # Query that filters out rejected quotes
        active_quotes = Invoice.objects.filter(
            user=self.user,
            client=self.client_obj,
            is_quote=True
        ).exclude(quote_status="REJECTED")
        
        # Rejected quote should not be in results
        self.assertNotIn(self.quote, active_quotes)

    def test_non_rejected_quotes_remain_visible(self):
        """Test that non-rejected quotes are still visible."""
        pending_quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            quote_status="PENDING",
            due_date=timezone.now().date() + timedelta(days=30)
        )
        
        accepted_quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            quote_status="ACCEPTED",
            due_date=timezone.now().date() + timedelta(days=30)
        )
        
        # Reject one
        self.quote.quote_status = "REJECTED"
        self.quote.save()
        
        # Query non-rejected
        active_quotes = Invoice.objects.filter(
            user=self.user,
            client=self.client_obj,
            is_quote=True
        ).exclude(quote_status="REJECTED")
        
        self.assertIn(pending_quote, active_quotes)
        self.assertIn(accepted_quote, active_quotes)
        self.assertNotIn(self.quote, active_quotes)

    def test_reject_does_not_affect_other_fields(self):
        """Test that rejecting a quote only changes quote_status."""
        original_is_quote = self.quote.is_quote
        original_client = self.quote.client
        original_status = self.quote.status
        
        self.quote.quote_status = "REJECTED"
        self.quote.save()
        
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.is_quote, original_is_quote)
        self.assertEqual(self.quote.client, original_client)
        self.assertEqual(self.quote.status, original_status)
        self.assertEqual(self.quote.quote_status, "REJECTED")


class QuoteWorkflowTransitionTest(TestCase):
    """Test complete quote acceptance and conversion workflow."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="transitiontest",
            email="test@example.com",
            password="testpass123"
        )
        self.profile = self.user.profile
        self.profile.company_name = "Test Company"
        self.profile.currency = "R"
        self.profile.save()
        
        self.client_obj = ClientModel.objects.create(
            user=self.user,
            name="Test Client",
            email="client@example.com"
        )

    def test_quote_lifecycle_pending_to_accepted_to_invoiced(self):
        """Test complete quote lifecycle: PENDING -> ACCEPTED -> INVOICED."""
        # Create quote
        quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT,
            quote_status="PENDING"
        )
        self.assertEqual(quote.quote_status, "PENDING")
        self.assertTrue(quote.is_quote)

        # Accept and convert
        quote.is_quote = False
        quote.was_originally_quote = True
        quote.quote_status = "ACCEPTED"
        quote.status = Invoice.Status.DRAFT
        quote.save()
        
        self.assertEqual(quote.quote_status, "ACCEPTED")
        self.assertFalse(quote.is_quote)
        self.assertTrue(quote.was_originally_quote)

        # Send (in real workflow)
        quote.is_emailed = True
        quote.emailed_at = timezone.now()
        quote.status = Invoice.Status.PENDING
        quote.save()
        
        self.assertTrue(quote.is_emailed)

    def test_quote_lifecycle_pending_to_rejected(self):
        """Test quote rejection: PENDING -> REJECTED."""
        quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT,
            quote_status="PENDING"
        )
        
        # Reject
        quote.quote_status = "REJECTED"
        quote.save()
        
        self.assertEqual(quote.quote_status, "REJECTED")
        self.assertTrue(quote.is_quote)

    def test_multiple_quotes_can_coexist(self):
        """Test that multiple quotes for same client can exist in different states."""
        quote1 = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            quote_status="PENDING",
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT
        )
        
        quote2 = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            quote_status="ACCEPTED",
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT
        )
        
        quote3 = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            quote_status="REJECTED",
            due_date=timezone.now().date() + timedelta(days=30),
            status=Invoice.Status.DRAFT
        )
        
        # All three exist
        all_quotes = Invoice.objects.filter(
            user=self.user,
            client=self.client_obj,
            is_quote=True
        )
        self.assertEqual(all_quotes.count(), 3)
        
        # Active quotes (non-rejected)
        active_quotes = all_quotes.exclude(quote_status="REJECTED")
        self.assertEqual(active_quotes.count(), 2)
