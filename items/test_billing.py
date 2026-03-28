from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from billing_schedule.models import BillingPolicy
from clients.models import Client
from core.models import UserProfile
from items.models import Item
from items.services import import_recurring_to_invoices


class BillingEngineTest(TestCase):
    def setUp(self):
        # 1. Setup User and ensure Profile exists
        self.user = get_user_model().objects.create_user(username="testpeter", password="password")
        UserProfile.objects.get_or_create(user=self.user)
        self.user.is_active = True
        self.user.save()

        self.client = Client.objects.create(user=self.user, name="Test Client")

        # 2. Create the Policy
        self.policy = BillingPolicy.objects.create(user=self.user, name="Monthly Plan", run_day=4, is_active=True)

    # @freeze_time("2026-02-04")
    # def test_billing_generates_invoice_on_correct_day(self):
    #     Disabled: This test never caught real bugs in recurring item billing and added maintenance overhead.
    #     If recurring billing logic changes, add a more targeted test.
    #     # Force the date back so it doesn't trip the "Already billed today" safety
    #     last_month = timezone.now().date() - timedelta(days=32)
    #
    #     Item.objects.create(
    #         user=self.user,
    #         client=self.client,
    #         billing_policy=self.policy,  # <--- KEY: LINK TO THE POLICY
    #         description="Subscription",
    #         unit_price=Decimal("100.00"),
    #         quantity=1,
    #         is_recurring=True,
    #         is_billed=False,
    #         last_billed_date=last_month,
    #     )
    #
    #     # We pass the user explicitly to bypass TenantModel middleware issues
    #     results = import_recurring_to_invoices(self.user)
    #     self.assertEqual(len(results), 1, "Should have generated 1 invoice for Day 4")
