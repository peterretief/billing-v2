import os
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice

from decimal import Decimal

User = get_user_model()


class BaseBillingTest(TestCase):
    """Base class providing unique setup and authentication for all billing tests."""

    def setUp(self):
        super().setUp()
        self.unique_id = uuid.uuid4().hex[:6]
        self.password = "password123"

        # 1. Create a unique user
        self.user = User.objects.create_user(
            username=f"user_{self.unique_id}", email=f"test_{self.unique_id}@example.com", password=self.password
        )

        # 2. Log in the test client
        self.test_client = TestClient()
        self.test_client.login(username=self.user.username, password=self.password)

        # 3. Create profile
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()

        # 4. Create a default client for convenience
        self.client_obj = Client.objects.create(
            user=self.user, name=f"Test Client {self.unique_id}", client_code=f"CL-{self.unique_id[:4].upper()}"
        )

    def create_test_invoice(self, **kwargs):
        """Helper to create an invoice with a guaranteed unique number and valid dates."""

        today = timezone.now().date()
        unique_num = f"INV-{uuid.uuid4().hex[:8].upper()}"

        defaults = {
            "user": self.user,
            "client": self.client_obj,
            "number": unique_num,
            "status": "DRAFT",
            "date_issued": today,
            "due_date": today + timedelta(days=14),
        }
        defaults.update(kwargs)
        return Invoice.objects.create(**defaults)


class AssetsTestCase(TestCase):
    def test_static_assets_are_localized(self):
        """Verify that critical JS/CSS files exist."""
        required_files = ["js/htmx.min.js", "css/bootstrap.min.css"]
        for file_path in required_files:
            found = False
            # Check dirs
            for loc in getattr(settings, "STATICFILES_DIRS", []):
                if os.path.exists(os.path.join(loc, file_path)):
                    found = True
                    break
            # Check root
            if not found and settings.STATIC_ROOT:
                if os.path.exists(os.path.join(settings.STATIC_ROOT, file_path)):
                    found = True
            self.assertTrue(found, f"{file_path} is missing from static folders!")


class InvoiceItemIntegrityTests(BaseBillingTest):
    def test_invoice_total_matches_items(self):
        """Invoice total_amount should match sum of item totals after linking items."""
        from items.models import Item
        from invoices.models import Invoice

        invoice = self.create_test_invoice(status="DRAFT")
        # Create and link items
        item1 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Service A",
            quantity=2,
            unit_price=Decimal("100.00"),
        )
        item2 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Service B",
            quantity=1,
            unit_price=Decimal("250.00"),
        )
        # Recalculate totals
        invoice.sync_totals()
        invoice.save()
        expected_total = item1.total + item2.total
        self.assertEqual(invoice.total_amount, expected_total)

    def test_no_item_duplication_on_relink(self):
        """An item cannot be linked to multiple invoices (should only belong to one)."""
        from items.models import Item
        from invoices.models import Invoice

        invoice1 = self.create_test_invoice(status="DRAFT")
        invoice2 = self.create_test_invoice(status="DRAFT")
        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice1,
            description="Unique Service",
            quantity=1,
            unit_price=Decimal("100.00"),
        )
        # Try to link to another invoice
        item.invoice = invoice2
        item.save()
        self.assertEqual(item.invoice, invoice2)
        self.assertEqual(invoice1.billed_items.count(), 0)
        self.assertEqual(invoice2.billed_items.count(), 1)

    def test_no_zero_total_invoices_with_items(self):
        """No invoice with items should have total_amount=0 after sync_totals."""
        from items.models import Item
        from invoices.models import Invoice

        invoice = self.create_test_invoice(status="DRAFT")
        item = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description="Service",
            quantity=1,
            unit_price=Decimal("100.00"),
        )
        invoice.sync_totals()
        invoice.save()
        self.assertNotEqual(invoice.total_amount, 0)
