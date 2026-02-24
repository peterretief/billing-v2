from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client
from invoices.models import Invoice
from items.models import Item

User = get_user_model()


class InvoiceDetailViewTest(TestCase):
    """Tests for the invoice detail view."""

    def setUp(self):
        """Set up data for the tests."""
        self.user = User.objects.create_user(username="testuser", password="password")
        from core.models import UserProfile

        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.initial_setup_complete = True
        profile.save()
        self.client_model = Client.objects.create(user=self.user, name="Test Client")
        today = timezone.now().date()
        self.invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_model,
            number="INV-001",
            status="DRAFT",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            invoice=self.invoice,
            user=self.user,
            client=self.client_model,
            description="Test Item",
            quantity=1,
            unit_price=Decimal("100.00"),
        )
        self.invoice.save()  # Recalculate totals
        self.client = DjangoClient()

    def test_invoice_detail_page_renders(self):
        """Test that the invoice detail page renders correctly."""
        self.client.login(username="testuser", password="password")
        url = reverse("invoices:invoice_detail", args=[self.invoice.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "invoices/invoice_detail.html")
        # Check for invoice number (may be split across lines in HTML)
        self.assertContains(response, self.invoice.number)
        self.assertContains(response, self.client_model.name)
        self.assertContains(response, "100.00")
