from django.test import TestCase



# Create your tests here.
from decimal import Decimal
from django.test import TestCase, Client as TestClient
from django.contrib.auth import get_user_model
from invoices.models import Invoice, InvoiceItem, VATReport, Payment
from core.models import UserProfile
from timesheets.models import TimesheetEntry
from items.models import Item
from clients.models import Client

from django.utils import timezone
from datetime import timedelta


User = get_user_model()

class BillingLogicTest(TestCase):
    def setUp(self):
        """Set up shared data for both test cases."""
        self.user = User.objects.create_user(username='tester', password='pass')
        
        # Explicitly create the profile for the test user
        self.profile, created = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.company_name = "Test Company"
        self.profile.save()
        
        self.client = Client.objects.create(
            user=self.user, 
            name="Test Client", 
            client_code="TST"
        )



    def test_standard_timesheet_billing(self):
        """Verify that standard InvoiceItems calculate correctly."""
        today = timezone.now().date()
        invoice = Invoice.objects.create(
            user=self.user,
            client=self.client,
            status='DRAFT',
            date_issued=today,
            due_date=today + timedelta(days=14) # Fix: Adding the required due_date
        )
        
        # Add a standard item (e.g., 5 hours @ 100)
        InvoiceItem.objects.create(
            invoice=invoice,
            description="Development Work",
            quantity=Decimal('5.00'),
            unit_price=Decimal('100.00')
        )
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal('500.00'))
        print(f"Standard Billing Success: {invoice.number} total is {invoice.total_amount}")


class DashboardTotalsTest(TestCase):
    """Test that dashboard totals are calculated correctly."""
    
    def setUp(self):
        """Set up test user and client."""
        self.user = User.objects.create_user(username='dashboard_tester', password='pass')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()
        
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Test Client",
            client_code="DASH"
        )
        
        self.client = TestClient()
        self.client.login(username='dashboard_tester', password='pass')

    def test_unbilled_timesheet_calculation(self):
        """Verify unbilled timesheet totals are calculated correctly."""
        # Create unbilled timesheets
        timesheet1 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            hours=Decimal('5.00'),
            hourly_rate=Decimal('100.00'),
            description="Dev Work",
            is_billed=False
        )
        
        timesheet2 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            hours=Decimal('3.50'),
            hourly_rate=Decimal('80.00'),
            description="Design Work",
            is_billed=False
        )
        
        # Create a billed timesheet (should not be included)
        timesheet3 = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            hours=Decimal('2.00'),
            hourly_rate=Decimal('100.00'),
            description="Billed Work",
            is_billed=True
        )
        
        # Expected: (5 * 100) + (3.5 * 80) = 500 + 280 = 780
        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)
        
        unbilled_ts_value = response.context['unbilled_timesheet_value']
        unbilled_ts_hours = response.context['unbilled_timesheet_hours']
        
        self.assertEqual(unbilled_ts_value, Decimal('780.00'))
        self.assertEqual(unbilled_ts_hours, Decimal('8.50'))
        print(f"✓ Unbilled Timesheets: R {unbilled_ts_value} ({unbilled_ts_hours} hours)")

    def test_unbilled_items_calculation(self):
        """Verify unbilled items totals are calculated correctly."""
        # Create unbilled items
        item1 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Widget A",
            quantity=Decimal('10.00'),
            unit_price=Decimal('50.00'),
            is_billed=False
        )
        
        item2 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Widget B",
            quantity=Decimal('5.00'),
            unit_price=Decimal('75.00'),
            is_billed=False
        )
        
        # Create a billed item (should not be included)
        item3 = Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Billed Widget",
            quantity=Decimal('2.00'),
            unit_price=Decimal('100.00'),
            is_billed=True
        )
        
        # Expected: (10 * 50) + (5 * 75) = 500 + 375 = 875
        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)
        
        unbilled_items_value = response.context['unbilled_items_value']
        self.assertEqual(unbilled_items_value, Decimal('875.00'))
        print(f"✓ Unbilled Items: R {unbilled_items_value}")

    def test_combined_unbilled_total(self):
        """Verify total unbilled (timesheets + items) is correct."""
        # Create unbilled timesheets
        TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            hours=Decimal('5.00'),
            hourly_rate=Decimal('100.00'),
            description="Dev Work",
            is_billed=False
        )
        
        # Create unbilled items
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Widget",
            quantity=Decimal('10.00'),
            unit_price=Decimal('50.00'),
            is_billed=False
        )
        
        # Expected: 500 (timesheet) + 500 (items) = 1000
        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)
        
        unbilled_ts = response.context['unbilled_timesheet_value']
        unbilled_items = response.context['unbilled_items_value']
        unbilled_total = response.context['unbilled_value']
        
        expected_total = unbilled_ts + unbilled_items
        self.assertEqual(unbilled_total, expected_total)
        self.assertEqual(unbilled_total, Decimal('1000.00'))
        print(f"✓ Combined Unbilled Total: R {unbilled_total} (TS: {unbilled_ts} + Items: {unbilled_items})")

    def test_billed_items_excluded(self):
        """Verify that billed timesheets and items are excluded."""
        # Create billed entries
        TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            hours=Decimal('10.00'),
            hourly_rate=Decimal('100.00'),
            description="Billed TS",
            is_billed=True
        )
        
        Item.objects.create(
            user=self.user,
            client=self.client_obj,
            description="Billed Item",
            quantity=Decimal('20.00'),
            unit_price=Decimal('100.00'),
            is_billed=True
        )
        
        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)
        
        unbilled_ts = response.context['unbilled_timesheet_value']
        unbilled_items = response.context['unbilled_items_value']
        
        self.assertEqual(unbilled_ts, Decimal('0.00'))
        self.assertEqual(unbilled_items, Decimal('0.00'))
        print("✓ Billed items correctly excluded from unbilled totals")

    def test_other_user_data_excluded(self):
        """Verify that other users' data doesn't affect totals."""
        # Create another user with their own data (use unique email)
        other_user = User.objects.create_user(
            username='other_user', 
            email='other@test.com',
            password='pass'
        )
        other_profile, _ = UserProfile.objects.get_or_create(user=other_user)
        other_client = Client.objects.create(
            user=other_user,
            name="Other Client",
            client_code="OTH"
        )
        
        # Create unbilled entries for the other user
        TimesheetEntry.objects.create(
            user=other_user,
            client=other_client,
            hours=Decimal('100.00'),
            hourly_rate=Decimal('1000.00'),
            description="Other's Work",
            is_billed=False
        )
        
        # Create unbilled entry for our test user
        TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            hours=Decimal('5.00'),
            hourly_rate=Decimal('100.00'),
            description="Our Work",
            is_billed=False
        )
        
        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)
        
        unbilled_ts = response.context['unbilled_timesheet_value']
        # Should only be 500 (our user's data), not 100500 (including other user)
        self.assertEqual(unbilled_ts, Decimal('500.00'))
        print("✓ Other users' data correctly excluded from totals")

    def test_empty_dashboard_totals(self):
        """Verify dashboard works correctly when no unbilled items exist."""
        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)
        
        unbilled_ts = response.context['unbilled_timesheet_value']
        unbilled_items = response.context['unbilled_items_value']
        unbilled_total = response.context['unbilled_value']
        
        self.assertEqual(unbilled_ts, Decimal('0.00'))
        self.assertEqual(unbilled_items, Decimal('0.00'))
        self.assertEqual(unbilled_total, Decimal('0.00'))
        print("✓ Empty dashboard displays correct zero totals")


class PaymentValidationTest(TestCase):
    """Test that payment validation prevents overpayments."""
    
    def setUp(self):
        """Set up test user and invoice."""
        self.user = User.objects.create_user(username='payment_tester', password='pass')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.is_vat_registered = False
        self.profile.save()
        
        self.client_obj = Client.objects.create(
            user=self.user,
            name="Payment Test Client",
            client_code="PAY"
        )
        
        self.invoice = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            status='DRAFT',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14)
        )
        
        # Add items to make total R500
        InvoiceItem.objects.create(
            invoice=self.invoice,
            description="Test Item",
            quantity=Decimal('5.00'),
            unit_price=Decimal('100.00')
        )
        
        # Update totals using the manager
        Invoice.objects.update_totals(self.invoice)
        self.invoice.refresh_from_db()

    def test_payment_under_balance_succeeds(self):
        """Verify that payments under balance due are accepted."""
        self.assertEqual(self.invoice.balance_due, Decimal('500.00'))
        
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('200.00'),
            reference='Test Payment'
        )
        
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('300.00'))
        print("✓ Partial payment (R200 of R500) accepted")

    def test_payment_equal_to_balance_succeeds(self):
        """Verify that payments equal to balance due are accepted."""
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('500.00'),
            reference='Full Payment'
        )
        
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('0.00'))
        self.assertEqual(self.invoice.status, 'PAID')
        print("✓ Full payment (R500) accepted and invoice marked paid")

    def test_payment_exceeds_balance_rejected(self):
        """Verify that payments exceeding balance due are rejected."""
        from django.core.exceptions import ValidationError
        
        with self.assertRaises(ValidationError) as context:
            payment = Payment(
                invoice=self.invoice,
                amount=Decimal('600.00'),
                reference='Overpayment'
            )
            payment.full_clean()
        
        self.assertIn('cannot exceed', str(context.exception))
        print("✓ Overpayment (R600 of R500) rejected with validation error")

    def test_zero_payment_rejected(self):
        """Verify that zero or negative payments are rejected."""
        from django.core.exceptions import ValidationError
        
        with self.assertRaises(ValidationError) as context:
            payment = Payment(
                invoice=self.invoice,
                amount=Decimal('0.00'),
                reference='Zero Payment'
            )
            payment.full_clean()
        
        self.assertIn('greater than zero', str(context.exception))
        print("✓ Zero payment rejected")

    def test_multiple_partial_payments(self):
        """Verify that multiple partial payments accumulate correctly."""
        # First payment
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('200.00'),
            reference='Payment 1'
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('300.00'))
        
        # Second payment
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('150.00'),
            reference='Payment 2'
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('150.00'))
        self.assertNotEqual(self.invoice.status, 'PAID')
        
        # Third payment (final)
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('150.00'),
            reference='Payment 3'
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, Decimal('0.00'))
        self.assertEqual(self.invoice.status, 'PAID')
        print("✓ Multiple payments (R200 + R150 + R150 = R500) handled correctly")