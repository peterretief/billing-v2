from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from billing_schedule.models import BillingPolicy
from clients.models import Client
from core.models import UserProfile
from items.models import Item
from items.services import import_recurring_to_invoices


class RecurringInvoicingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="recurring_test", email="rtest@example.com", password="pw")

        # Consistent Profile Setup
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.company_name = "TestCo"
        profile.business_email = "biz@testco.example"
        profile.save()

    @patch("items.services.email_item_invoice_to_client")  # Use the service-layer path
    @patch("invoices.utils.generate_invoice_pdf")
    def test_import_recurring_creates_invoice_and_emails(self, mock_pdf, mock_email):
        # 1. Setup Mocks
        mock_email.return_value = True
        mock_pdf.return_value = b"%PDF-test"

        # 2. Setup Client & Policy
        client = Client.objects.create(user=self.user, name="Client A", email="clienta@example.com", payment_terms=14)

        today_day = timezone.now().day
        policy = BillingPolicy.objects.create(user=self.user, run_day=today_day, is_active=True)

        # 3. Create Item LINKED to Policy and in the PAST
        past_date = timezone.now().date() - timedelta(days=32)
        Item.objects.create(
            user=self.user,
            client=client,
            billing_policy=policy,  # Crucial Link
            description="Recurring service",
            quantity=1,
            unit_price=Decimal("100.00"),
            is_recurring=True,
            is_taxable=True,
            last_billed_date=past_date,  # Crucial Date
        )

        # 4. Run and Verify
        created_invoices = import_recurring_to_invoices(self.user)

        self.assertEqual(len(created_invoices), 1, "The service should return 1 processed invoice")
        self.assertEqual(created_invoices[0].client, client)
        self.assertTrue(mock_email.called)
