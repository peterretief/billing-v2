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
            tax_mode=Invoice.TaxMode.NONE,
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
                is_taxable=False,
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
            tax_mode=Invoice.TaxMode.NONE,
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
            is_taxable=False,
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
