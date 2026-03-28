"""
Tests for invoice item grouping with Decimal precision edge cases.

This test module specifically addresses the bug where timesheets with the same
category and rate but different Decimal representations (e.g., Decimal('250')
vs Decimal('250.00')) would not group correctly in invoice rendering.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from core.tests import BaseBillingTest
from invoices.models import Invoice
from invoices.utils import build_invoice_items_list
from timesheets.models import TimesheetEntry, WorkCategory

User = get_user_model()


class InvoiceGroupingDecimalPrecisionTests(BaseBillingTest):
    """Test that invoice grouping handles Decimal precision correctly."""

    def setUp(self):
        super().setUp()
        self.category = WorkCategory.objects.create(
            user=self.user,
            name="Consulting"
        )
        # Create invoice
        from datetime import timedelta
        self.invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
            status="DRAFT",
        )

    def test_grouping_with_same_rate_different_precisions(self):
        """
        Verify that timesheets with identical rates but different Decimal
        precisions (e.g., 250, 250.0, 250.00) are grouped into a single line item.
        
        This was the bug: Decimal('250') != Decimal('250.00') as dict keys,
        causing timesheets to not group.
        """
        # Create two timesheets with same category and rate but different Decimal precision
        entry1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("5.00"),
            hourly_rate=Decimal("250.00"),  # Two decimal places
            invoice=self.invoice,
        )
        entry2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("4.75"),
            hourly_rate=Decimal("250"),  # No decimal places
            invoice=self.invoice,
        )

        # Refresh to apply normalization
        entry1.refresh_from_db()
        entry2.refresh_from_db()

        # Build invoice items list (this is what gets rendered in email/PDF)
        items = build_invoice_items_list(self.invoice)

        # Should have exactly ONE line item (grouped)
        self.assertEqual(len(items), 1, "Timesheets should be grouped into one line")

        # Verify the grouped item has correct totals
        item = items[0]
        self.assertEqual(item["description"], "Consulting")
        self.assertEqual(Decimal(item["quantity"]), Decimal("9.75"))  # 5.00 + 4.75
        self.assertEqual(Decimal(item["unit_price"]), Decimal("250.00"))
        self.assertEqual(Decimal(item["row_subtotal"].replace(",", "")), Decimal("2437.50"))  # 9.75 * 250

    def test_grouping_preserves_ungrouped_when_rates_differ(self):
        """
        Verify that timesheets with DIFFERENT rates stay separate.
        This is the inverse case - should NOT group.
        """
        entry1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("5.00"),
            hourly_rate=Decimal("250.00"),
            invoice=self.invoice,
        )
        entry2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("4.75"),
            hourly_rate=Decimal("300.00"),  # Different rate!
            invoice=self.invoice,
        )

        items = build_invoice_items_list(self.invoice)

        # Should have TWO line items (different rates don't group)
        self.assertEqual(len(items), 2, "Different rates should not be grouped")
        
        # First item
        self.assertEqual(Decimal(items[0]["quantity"]), Decimal("5.00"))
        self.assertEqual(Decimal(items[0]["unit_price"]), Decimal("250.00"))

        # Second item
        self.assertEqual(Decimal(items[1]["quantity"]), Decimal("4.75"))
        self.assertEqual(Decimal(items[1]["unit_price"]), Decimal("300.00"))

    def test_grouping_with_three_different_decimal_representations(self):
        """
        Stress test: three timesheets with same rate in different Decimal forms.
        """
        rates = [
            Decimal("250"),      # No decimal places
            Decimal("250.0"),    # One decimal place
            Decimal("250.00"),   # Two decimal places
        ]
        
        entries = []
        for i, rate in enumerate(rates):
            entry = TimesheetEntry.objects.create(
                user=self.user,
                client=self.client_obj,
                category=self.category,
                date=timezone.now().date(),
                hours=Decimal("1.00"),
                hourly_rate=rate,
                invoice=self.invoice,
            )
            entries.append(entry)

        # Refresh all
        for entry in entries:
            entry.refresh_from_db()

        items = build_invoice_items_list(self.invoice)

        # Should have exactly ONE line item
        self.assertEqual(len(items), 1, "All three should group into one line")
        
        # Verify totals
        item = items[0]
        self.assertEqual(Decimal(item["quantity"]), Decimal("3.00"))
        self.assertEqual(Decimal(item["unit_price"]), Decimal("250.00"))
        self.assertEqual(Decimal(item["row_subtotal"]), Decimal("750.00"))

    def test_grouping_multiple_categories_with_same_rate(self):
        """
        Verify that timesheets are grouped only by (category, rate) tuple.
        Different categories should not group together even with same rate.
        """
        category2 = WorkCategory.objects.create(
            user=self.user,
            name="Development"
        )
        
        # Same rate, different categories
        entry1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,  # Consulting
            date=timezone.now().date(),
            hours=Decimal("5.00"),
            hourly_rate=Decimal("250.00"),
            invoice=self.invoice,
        )
        entry2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=category2,  # Development
            date=timezone.now().date(),
            hours=Decimal("3.00"),
            hourly_rate=Decimal("250.00"),  # Same rate as above
            invoice=self.invoice,
        )

        items = build_invoice_items_list(self.invoice)

        # Should have TWO line items (different categories)
        self.assertEqual(len(items), 2, "Different categories should not group")
        
        descriptions = {item["description"] for item in items}
        self.assertEqual(descriptions, {"Consulting", "Development"})

    def test_grouping_with_rounding_cases(self):
        """
        Test edge cases with rounding (e.g., 250.001 rounded to 250.00).
        """
        # Create entries with values that round to the same normalized rate
        entry1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("5.00"),
            hourly_rate=Decimal("250.001"),  # Will round to 250.00
            invoice=self.invoice,
        )
        entry2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("3.00"),
            hourly_rate=Decimal("250.004"),  # Will also round to 250.00
            invoice=self.invoice,
        )

        # Refresh to apply normalization
        entry1.refresh_from_db()
        entry2.refresh_from_db()

        items = build_invoice_items_list(self.invoice)

        # Both should normalize to 250.00 and group together
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(Decimal(item["quantity"]), Decimal("8.00"))
        self.assertEqual(Decimal(item["unit_price"]), Decimal("250.00"))
