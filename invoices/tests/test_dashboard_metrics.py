from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice, Payment
from items.models import Item
from timesheets.models import TimesheetEntry

User = get_user_model()


class DashboardMetricsTest(TestCase):
    """Tests to verify dashboard card metrics are accurate."""

    def setUp(self):
        """Set up test user, client, and sample data."""
        self.user = User.objects.create_user(username="dashtest", password="testpass123")
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.company_name = "Dashboard Test Co"
        self.profile.initial_setup_complete = True
        self.profile.save()

        self.client_obj = Client.objects.create(
            user=self.user, name="Test Client", client_code="DASH"
        )

        self.today = timezone.now().date()

    def test_queued_items_count_and_value(self):
        """Verify Queued Items card displays correct count and total value."""
        self.client.force_login(self.user)
        
        # Create 3 queued (recurring) items
        for i in range(3):
            Item.objects.create(
                user=self.user,
                client=self.client_obj,
                is_billed=False,
                is_recurring=True,
                quantity=Decimal("2.00"),
                unit_price=Decimal("100.00"),
            )

        response = self.client.get(reverse("invoices:dashboard"))
        self.assertEqual(response.status_code, 200)

        context = response.context
        self.assertEqual(context["queued_items_count"], 3)
        self.assertEqual(context["queued_items_value"], Decimal("600.00"))

    def test_unbilled_wip_counts_and_value(self):
        """Verify Unbilled WIP displays correct counts (timesheets + items) and total value."""
        self.client.force_login(self.user)
        
        # Create 2 unbilled timesheets
        for i in range(2):
            TimesheetEntry.objects.create(
                user=self.user,
                client=self.client_obj,
                hours=Decimal("8.00"),
                hourly_rate=Decimal("50.00"),
                is_billed=False,
                date=self.today,
            )

        # Create 3 unbilled non-recurring items
        for i in range(3):
            Item.objects.create(
                user=self.user,
                client=self.client_obj,
                is_billed=False,
                is_recurring=False,
                quantity=Decimal("1.00"),
                unit_price=Decimal("100.00"),
            )

        response = self.client.get(reverse("invoices:dashboard"))
        self.assertEqual(response.status_code, 200)

        context = response.context
        # timesheets: 2 * 8 * 50 = 800
        # items: 3 * 1 * 100 = 300
        # total: 1100
        self.assertEqual(context["unbilled_ts_count"], 2)
        self.assertEqual(context["unbilled_items_count"], 3)
        self.assertEqual(context["unbilled_wip_value"], Decimal("1100.00"))

    def test_total_billed_invoices_count(self):
        """Verify Total Billed displays correct invoice count (excludes DRAFT/DISCARDED/CANCELLED)."""
        self.client.force_login(self.user)
        
        today = self.today

        # Create invoices with different statuses
        invoice_pending = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PENDING",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice_pending,
            quantity=Decimal("1.00"),
            unit_price=Decimal("500.00"),
        )
        invoice_pending.sync_totals()
        invoice_pending.save()

        invoice_paid = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PAID",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice_paid,
            quantity=Decimal("1.00"),
            unit_price=Decimal("300.00"),
        )
        invoice_paid.sync_totals()
        invoice_paid.save()

        invoice_draft = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="DRAFT",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice_draft,
            quantity=Decimal("1.00"),
            unit_price=Decimal("200.00"),
        )
        invoice_draft.sync_totals()
        invoice_draft.save()

        invoice_cancelled = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="CANCELLED",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )

        response = self.client.get(reverse("invoices:dashboard"))
        self.assertEqual(response.status_code, 200)

        context = response.context
        # Should count PENDING and PAID, but NOT DRAFT or CANCELLED
        self.assertEqual(context["total_billed_invoices"], 2)
        self.assertEqual(context["total_billed"], Decimal("800.00"))

    def test_outstanding_invoices_count(self):
        """Verify Outstanding displays correct count (unpaid invoices, excludes DRAFT/PAID)."""
        self.client.force_login(self.user)
        
        today = self.today

        # Create PENDING (unpaid) invoice
        invoice_pending = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PENDING",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice_pending,
            quantity=Decimal("1.00"),
            unit_price=Decimal("400.00"),
        )
        invoice_pending.sync_totals()
        invoice_pending.save()

        # Create OVERDUE (unpaid) invoice
        invoice_overdue = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="OVERDUE",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice_overdue,
            quantity=Decimal("1.00"),
            unit_price=Decimal("250.00"),
        )
        invoice_overdue.sync_totals()
        invoice_overdue.save()

        # Create PAID invoice (should not count)
        invoice_paid = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PAID",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice_paid,
            quantity=Decimal("1.00"),
            unit_price=Decimal("200.00"),
        )
        invoice_paid.sync_totals()
        invoice_paid.save()

        response = self.client.get(reverse("invoices:dashboard"))
        self.assertEqual(response.status_code, 200)

        context = response.context
        # Should count PENDING and OVERDUE, but NOT PAID
        self.assertEqual(context["outstanding_invoices_count"], 2)
        self.assertEqual(context["total_outstanding"], Decimal("650.00"))

    def test_pending_quotes_count(self):
        """Verify Pending Quotes displays correct count (is_quote=True)."""
        self.client.force_login(self.user)
        
        today = self.today

        # Create 2 quotes
        for i in range(2):
            quote = Invoice.objects.create(
                user=self.user,
                client=self.client_obj,
                is_quote=True,
                status="DRAFT",
                date_issued=today,
                due_date=today + timedelta(days=14),
            )
            Item.objects.create(
                user=self.user,
                client=self.client_obj,
                invoice=quote,
                quantity=Decimal("1.00"),
                unit_price=Decimal("300.00"),
            )
            quote.sync_totals()
            quote.save()

        # Create 1 regular invoice (should not count)
        regular_invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=False,
            status="DRAFT",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=regular_invoice,
            quantity=Decimal("1.00"),
            unit_price=Decimal("200.00"),
        )
        regular_invoice.sync_totals()
        regular_invoice.save()

        response = self.client.get(reverse("invoices:dashboard"))
        self.assertEqual(response.status_code, 200)

        context = response.context
        # Should count only quotes
        self.assertEqual(context["pending_quotes_count"], 2)
        self.assertEqual(context["total_quotes"], Decimal("600.00"))

    def test_payment_from_client_count(self):
        """Verify Payment from Client displays correct count of PAID invoices."""
        self.client.force_login(self.user)
        
        today = self.today

        # Create 2 PAID invoices
        for i in range(2):
            paid_invoice = Invoice.objects.create(
                user=self.user,
                client=self.client_obj,
                status="PAID",
                date_issued=today,
                due_date=today + timedelta(days=14),
            )
            Item.objects.create(
                user=self.user,
                client=self.client_obj,
                invoice=paid_invoice,
                quantity=Decimal("1.00"),
                unit_price=Decimal("250.00"),
            )
            paid_invoice.sync_totals()
            paid_invoice.save()

        # Create 1 PENDING invoice (should not count)
        pending_invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PENDING",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=pending_invoice,
            quantity=Decimal("1.00"),
            unit_price=Decimal("200.00"),
        )
        pending_invoice.sync_totals()
        pending_invoice.save()

        response = self.client.get(reverse("invoices:dashboard"))
        self.assertEqual(response.status_code, 200)

        context = response.context
        # Should count only PAID invoices (dashbaord shows count from paid_invoices queryset)
        self.assertEqual(len(context["paid_invoices"]), 2)

    def test_all_metrics_together(self):
        """Integration test: verify all metrics work together correctly."""
        self.client.force_login(self.user)
        
        today = self.today

        # Queued items: 2
        for i in range(2):
            Item.objects.create(
                user=self.user,
                client=self.client_obj,
                is_recurring=True,
                quantity=Decimal("1.00"),
                unit_price=Decimal("50.00"),
            )

        # Unbilled timesheets: 1
        TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            hours=Decimal("5.00"),
            hourly_rate=Decimal("100.00"),
            is_billed=False,
            date=today,
        )

        # Unbilled items: 1
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            is_recurring=False,
            quantity=Decimal("2.00"),
            unit_price=Decimal("75.00"),
        )

        # Billed invoices: 2 (PENDING, PAID)
        invoice_pending = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PENDING",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice_pending,
            quantity=Decimal("1.00"),
            unit_price=Decimal("400.00"),
        )
        invoice_pending.sync_totals()
        invoice_pending.save()

        invoice_paid = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status="PAID",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice_paid,
            quantity=Decimal("1.00"),
            unit_price=Decimal("300.00"),
        )
        invoice_paid.sync_totals()
        invoice_paid.save()
        
        # Create payment for the PAID invoice
        Payment.objects.create(
            user=self.user,
            invoice=invoice_paid,
            amount=Decimal("300.00"),
            date_paid=today,
        )

        # Quote: 1
        quote = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            is_quote=True,
            status="DRAFT",
            date_issued=today,
            due_date=today + timedelta(days=14),
        )
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=quote,
            quantity=Decimal("1.00"),
            unit_price=Decimal("200.00"),
        )
        quote.sync_totals()
        quote.save()

        response = self.client.get(reverse("invoices:dashboard"))
        self.assertEqual(response.status_code, 200)

        context = response.context

        # Verify all counts
        self.assertEqual(context["queued_items_count"], 2)
        self.assertEqual(context["unbilled_ts_count"], 1)
        self.assertEqual(context["unbilled_items_count"], 1)
        self.assertEqual(context["total_billed_invoices"], 2)
        self.assertEqual(context["outstanding_invoices_count"], 1)
        self.assertEqual(context["pending_quotes_count"], 1)

        # Verify all values
        self.assertEqual(context["queued_items_value"], Decimal("100.00"))
        self.assertEqual(context["unbilled_wip_value"], Decimal("650.00"))
        self.assertEqual(context["total_billed"], Decimal("700.00"))
        self.assertEqual(context["total_outstanding"], Decimal("400.00"))
        self.assertEqual(context["total_quotes"], Decimal("200.00"))
        self.assertEqual(context["total_paid_invoices"], Decimal("300.00"))
