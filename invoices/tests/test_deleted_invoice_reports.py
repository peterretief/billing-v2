import uuid
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

User = get_user_model()


class DeletedInvoiceReportTest(TestCase):
    """Tests to ensure deleted invoices don't appear in reports or dashboards."""

    def setUp(self):
        """Set up test data with unique attributes to prevent database collisions."""
        unique_id = uuid.uuid4().hex[:6]
        self.username = f"testuser_{unique_id}"
        self.password = "testpass123"

        self.user = User.objects.create_user(
            username=self.username, password=self.password, email=f"test_{unique_id}@example.com"
        )

        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.company_name = "Test Company"
        self.profile.monthly_target = Decimal("10000.00")
        self.profile.initial_setup_complete = True
        self.profile.save()

        self.client_obj = Client.objects.create(
            user=self.user, name="Test Client", email=f"client_{unique_id}@test.com"
        )

        self.test_client = TestClient()
        self.test_client.login(username=self.username, password=self.password)

        today = timezone.now().date()

        # Unique invoice numbers are critical for database constraints
        self.invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=f"DRAFT-{unique_id}",
            status="DRAFT",
            date_issued=today,
            due_date=today + timedelta(days=14),
            billing_type="SERVICE",
            subtotal_amount=Decimal("5000.00"),
            tax_amount=Decimal("750.00"),
            total_amount=Decimal("5750.00"),
        )

        self.posted_invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number=f"POST-{unique_id}",
            status="PENDING",
            date_issued=today,
            due_date=today + timedelta(days=14),
            billing_type="SERVICE",
            subtotal_amount=Decimal("3000.00"),
            tax_amount=Decimal("450.00"),
            total_amount=Decimal("3450.00"),
        )

    def test_deleted_invoice_not_in_invoice_list(self):
        """Test that deleted invoices don't appear in invoice list."""
        response = self.test_client.get(reverse("invoices:invoice_list"))
        initial_invoices = response.context["invoices"].paginator.count

        self.test_client.post(reverse("invoices:delete_invoice", args=[self.invoice.pk]))

        response = self.test_client.get(reverse("invoices:invoice_list"))
        after_deletion_count = response.context["invoices"].paginator.count
        self.assertEqual(after_deletion_count, initial_invoices - 1)

    def test_deleted_invoice_completely_removed_from_database(self):
        """Test that deleted invoices are removed from the database."""
        invoice_id = self.invoice.pk
        self.assertTrue(Invoice.objects.filter(pk=invoice_id).exists())

        response = self.test_client.post(reverse("invoices:delete_invoice", args=[invoice_id]))
        self.assertEqual(response.status_code, 302)  # Should redirect after success
        self.assertFalse(Invoice.objects.filter(pk=invoice_id).exists())

    def test_deleted_invoice_not_in_any_queryset(self):
        """Test that deleted invoices are excluded from querysets."""
        all_invoices_before = Invoice.objects.filter(user=self.user)
        self.assertEqual(all_invoices_before.count(), 2)

        self.test_client.post(reverse("invoices:delete_invoice", args=[self.invoice.pk]))

        all_invoices_after = Invoice.objects.filter(user=self.user)
        self.assertEqual(all_invoices_after.count(), 1)

    def test_only_current_user_invoices_in_reports(self):
        """Test that deleting another user's invoice doesn't affect current user."""
        other_unique_id = uuid.uuid4().hex[:6]
        other_username = f"otheruser_{other_unique_id}"
        other_password = "otherpass123"

        other_user = User.objects.create_user(
            username=other_username, email=f"other_{other_unique_id}@test.com", password=other_password
        )

        # Create invoice for other user
        other_invoice = Invoice.objects.create(
            user=other_user,
            client=self.client_obj,
            number=f"OTHER-{other_unique_id}",
            status="DRAFT",
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14),
            total_amount=Decimal("2000.00"),
        )

        # Verify initial counts
        self.assertEqual(Invoice.objects.filter(user=self.user).count(), 2)
        self.assertEqual(Invoice.objects.filter(user=other_user).count(), 1)

        # 1. Login as the other user
        other_client = TestClient()
        logged_in = other_client.login(username=other_username, password=other_password)
        self.assertTrue(logged_in, "Other user failed to log in")

        # 2. Delete the invoice as the other user
        response = other_client.post(reverse("invoices:delete_invoice", args=[other_invoice.pk]), follow=True)

        # Verify response landed on the list page
        self.assertEqual(response.status_code, 200)

        # 3. Verify Other User's invoice is gone
        self.assertEqual(Invoice.objects.filter(user=other_user).count(), 0)

        # 4. Verify Current User's invoices are untouched
        self.assertEqual(Invoice.objects.filter(user=self.user).count(), 2)
