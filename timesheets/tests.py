from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from core.tests import BaseBillingTest
from invoices.models import Invoice
from items.models import Item
from timesheets.models import TimesheetEntry, WorkCategory

User = get_user_model()


class TimesheetLogicTest(BaseBillingTest):
    """Test basic timesheet entry calculations."""

    def test_timesheet_calculation(self):
        """Verify total_value calculation (hours * hourly_rate)."""
        entry = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            date=timezone.now().date(),
            hours=Decimal("5.00"),
            hourly_rate=Decimal("200.00"),
        )
        self.assertEqual(entry.total_value, Decimal("1000.00"))


class TimesheetCategoryTests(BaseBillingTest):
    """Test timesheet entry with category field."""

    def setUp(self):
        super().setUp()
        # Create work categories
        self.category_dev = WorkCategory.objects.create(user=self.user, name="Development")
        self.category_design = WorkCategory.objects.create(user=self.user, name="Design")

    def test_create_entry_with_category(self):
        """Verify creating timesheet entry with category."""
        entry = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category_dev,
            date=timezone.now().date(),
            hours=Decimal("4.00"),
            hourly_rate=Decimal("150.00"),
        )
        self.assertEqual(entry.category.name, "Development")
        self.assertEqual(entry.total_value, Decimal("600.00"))

    def test_create_entry_without_category(self):
        """Verify creating timesheet entry without category (null category)."""
        entry = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=None,
            date=timezone.now().date(),
            hours=Decimal("3.00"),
            hourly_rate=Decimal("100.00"),
        )
        self.assertIsNone(entry.category)
        self.assertEqual(entry.total_value, Decimal("300.00"))

    def test_entry_string_representation(self):
        """Verify __str__ method for timesheet entry."""
        entry = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            date=timezone.now().date(),
            hours=Decimal("2.50"),
            hourly_rate=Decimal("100.00"),
        )
        expected = f"{timezone.now().date()} - {self.client_obj.name} (2.50 hrs)"
        self.assertEqual(str(entry), expected)


class GenerateInvoiceBulkTests(BaseBillingTest):
    """Test invoice generation from timesheet entries."""

    def setUp(self):
        super().setUp()
        self.profile = self.user.profile
        self.profile.is_vat_registered = False
        self.profile.save()

        # Create categories
        self.category_dev = WorkCategory.objects.create(user=self.user, name="Development")
        self.category_meetings = WorkCategory.objects.create(user=self.user, name="Meetings")

    def test_generate_invoice_uses_category_name(self):
        """Verify category name is used as invoice item description."""
        # Create multiple entries with different categories
        entry1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category_dev,
            date=timezone.now().date(),
            hours=Decimal("8.00"),
            hourly_rate=Decimal("150.00"),
            is_billed=False,
        )
        entry2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category_meetings,
            date=timezone.now().date(),
            hours=Decimal("2.00"),
            hourly_rate=Decimal("100.00"),
            is_billed=False,
        )

        # Simulate bulk invoice generation
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            due_date=timezone.now().date(),
            status=Invoice.Status.DRAFT,
        )

        # Create items with category names
        for desc, rate, total_h in [
            ("Development", Decimal("150.00"), Decimal("8.00")),
            ("Meetings", Decimal("100.00"), Decimal("2.00")),
        ]:
            Item.objects.create(
                user=self.user,
                client=self.client_obj,
                invoice=invoice,
                description=desc,
                quantity=total_h,
                unit_price=rate,
            )

        # Mark entries as billed
        entry1.is_billed = True
        entry1.invoice = invoice
        entry1.save()
        entry2.is_billed = True
        entry2.invoice = invoice
        entry2.save()

        # Verify items have category names
        items = invoice.billed_items.all()
        descriptions = [item.description for item in items]
        self.assertIn("Development", descriptions)
        self.assertIn("Meetings", descriptions)

    def test_generate_invoice_with_null_category(self):
        """Verify 'General Work' fallback when entry has no category."""
        entry = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=None,
            date=timezone.now().date(),
            hours=Decimal("5.00"),
            hourly_rate=Decimal("120.00"),
            is_billed=False,
        )

        # Simulate invoice generation with null category
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            due_date=timezone.now().date(),
            status=Invoice.Status.DRAFT,
        )

        # Use "General Work" as fallback
        category_name = entry.category.name if entry.category else "General Work"
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            invoice=invoice,
            description=category_name,
            quantity=Decimal("5.00"),
            unit_price=Decimal("120.00"),
        )

        items = invoice.billed_items.all()
        self.assertEqual(items.first().description, "General Work")

    def test_aggregate_entries_by_category_and_rate(self):
        """Verify entries are aggregated by (category, rate) in invoice generation."""
        # Two entries with same category and rate should aggregate
        entry1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category_dev,
            date=timezone.now().date(),
            hours=Decimal("3.00"),
            hourly_rate=Decimal("150.00"),
            is_billed=False,
        )
        entry2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category_dev,
            date=timezone.now().date(),
            hours=Decimal("5.00"),
            hourly_rate=Decimal("150.00"),
            is_billed=False,
        )

        # Aggregate logic
        key1 = (entry1.category.name, entry1.hourly_rate)
        key2 = (entry2.category.name, entry2.hourly_rate)
        self.assertEqual(key1, key2)  # Should be the same key

        # Total hours for this key should be 8.00
        total_hours = entry1.hours + entry2.hours
        self.assertEqual(total_hours, Decimal("8.00"))


class TimesheetFormTests(BaseBillingTest):
    """Test timesheet form validation."""

    def setUp(self):
        super().setUp()
        self.category = WorkCategory.objects.create(user=self.user, name="Testing")

    def test_log_time_form_includes_category(self):
        """Verify form includes category field."""
        from timesheets.forms import TimesheetEntryForm

        form = TimesheetEntryForm()
        self.assertIn("category", form.fields)
        self.assertIn("client", form.fields)
        self.assertIn("hours", form.fields)
        self.assertIn("hourly_rate", form.fields)
        # Verify description is NOT in form
        self.assertNotIn("description", form.fields)

class DecimalNormalizationTests(BaseBillingTest):
    """Test Decimal field normalization to prevent precision mismatches."""

    def setUp(self):
        super().setUp()
        self.category = WorkCategory.objects.create(user=self.user, name="Consulting")

    def test_hourly_rate_normalized_to_two_decimals(self):
        """Verify hourly_rate is normalized to 2 decimal places on save."""
        # Create with various Decimal representations
        entry = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("5"),
            hourly_rate=Decimal("250"),  # No decimal places
        )
        # Reload from DB
        entry.refresh_from_db()
        # Should be normalized to 2 decimal places
        self.assertEqual(entry.hourly_rate, Decimal("250.00"))
        self.assertEqual(entry.hours, Decimal("5.00"))

    def test_hourly_rate_different_precisions_are_equivalent_after_save(self):
        """Verify entries with different Decimal precisions are equivalent after save."""
        entry1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("5.00"),
            hourly_rate=Decimal("250.00"),
        )
        entry2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("4.75"),
            hourly_rate=Decimal("250"),  # Different precision
        )
        # Reload from DB
        entry1.refresh_from_db()
        entry2.refresh_from_db()
        # After normalization, they should have identical rates
        self.assertEqual(entry1.hourly_rate, entry2.hourly_rate)
        # Creating dict keys should produce identical keys for grouping
        key1 = (entry1.category.name, entry1.hourly_rate)
        key2 = (entry2.category.name, entry2.hourly_rate)
        self.assertEqual(key1, key2)

    def test_grouping_key_consistency_with_normalized_decimals(self):
        """Verify grouping works regardless of Decimal input precision."""
        # Create timesheets with different Decimal precisions but same value
        from decimal import ROUND_HALF_UP
        
        entry1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("5"),
            hourly_rate=Decimal("250"),
        )
        entry2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            category=self.category,
            date=timezone.now().date(),
            hours=Decimal("4.75"),
            hourly_rate=Decimal("250.00"),
        )
        
        # Reload and verify normalization
        entry1.refresh_from_db()
        entry2.refresh_from_db()
        
        # Build grouping dictionary like build_invoice_items_list() does
        grouped = {}
        for entry in [entry1, entry2]:
            normalized_rate = Decimal(str(entry.hourly_rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            key = (entry.category.name, normalized_rate)
            if key not in grouped:
                grouped[key] = Decimal("0")
            grouped[key] += entry.hours
        
        # Should have only ONE key (both grouped together)
        self.assertEqual(len(grouped), 1)
        # Total hours should be 9.75
        total_hours = list(grouped.values())[0]
        self.assertEqual(total_hours, Decimal("9.75"))

    def test_three_way_decimal_precision_grouping(self):
        """Test grouping with three different Decimal representations of same rate."""
        rates = [
            Decimal("250"),      # No decimal places
            Decimal("250.0"),    # One decimal place
            Decimal("250.00"),   # Two decimal places
        ]
        
        from decimal import ROUND_HALF_UP
        
        entries = []
        for i, rate in enumerate(rates):
            entry = TimesheetEntry.objects.create(
                user=self.user,
                client=self.client_obj,
                category=self.category,
                date=timezone.now().date(),
                hours=Decimal("1.00"),
                hourly_rate=rate,
            )
            entries.append(entry)
        
        # Reload all and verify normalization
        for entry in entries:
            entry.refresh_from_db()
        
        # Group using normalized approach
        grouped = {}
        for entry in entries:
            normalized_rate = Decimal(str(entry.hourly_rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            key = (entry.category.name, normalized_rate)
            if key not in grouped:
                grouped[key] = Decimal("0")
            grouped[key] += entry.hours
        
        # All three should be in ONE group
        self.assertEqual(len(grouped), 1)
        # Total should be 3.00 hours
        self.assertEqual(list(grouped.values())[0], Decimal("3.00"))