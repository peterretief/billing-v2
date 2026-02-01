from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice, Payment, TaxPayment

User = get_user_model()


class DashboardCalculationsTest(TestCase):
    """Test that dashboard calculations are correct."""
    
    def setUp(self):
        """Set up test user and client."""
        self.user = User.objects.create_user(username='dashboard_tester', 
                                             password='pass')
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

    def test_tax_summary_calculation(self):
        """Verify tax_summary is calculated correctly."""
        self.profile.is_vat_registered = True
        self.profile.save()

        # Create some invoices with unique numbers
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="TAX-INV-01",  # Added unique number
            total_amount=Decimal('1150.00'),
            tax_amount=Decimal('150.00'),
            status='PAID',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="TAX-INV-02",  # Added unique number
            total_amount=Decimal('575.00'),
            tax_amount=Decimal('75.00'),
            status='PENDING',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        # Invoice with no tax
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="TAX-INV-03",  # Added unique number
            total_amount=Decimal('200.00'),
            tax_amount=Decimal('0.00'),
            status='PENDING',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        # VAT Payment
        TaxPayment.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            tax_type='VAT'
        )

        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)

        tax_summary = response.context['tax_summary']
        # vat_due is collected (from PAID invoices), 
        # vat_paid is paid, balance is outstanding
        self.assertEqual(tax_summary['collected'], Decimal('150.00'))
        self.assertEqual(tax_summary['paid'], Decimal('100.00'))
        self.assertEqual(tax_summary['outstanding'], Decimal('50.00'))
        print(f"✓ Tax Summary: Due: R{tax_summary['collected']}, "
              "Paid: R{tax_summary['paid']}, Balance: R{tax_summary['outstanding']}")

    def test_total_outstanding_calculation(self):
        """Verify total_outstanding is calculated correctly."""
        # Create some invoices with unique numbers
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="OUT-INV-01",
            total_amount=Decimal('1000.00'),
            status='PENDING',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="OUT-INV-02",
            total_amount=Decimal('500.00'),
            status='PAID',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="OUT-INV-03",
            total_amount=Decimal('200.00'),
            status='DRAFT',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        # Partially paid invoice
        invoice4 = Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="OUT-INV-04",
            total_amount=Decimal('1000.00'),
            status='PENDING',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        Payment.objects.create(
            invoice=invoice4,
            amount=Decimal('300.00'),
            user=self.user  # Added user for multi-tenancy
        )
        
        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)
        
        total_outstanding = response.context['total_outstanding']
        # outstanding = (1000 - 0) + (1000 - 300) = 1700
        self.assertEqual(total_outstanding, Decimal('1700.00'))
        print(f"✓ Total Outstanding: R {total_outstanding}")

    def test_total_billed_calculation(self):
        """Verify total_billed is calculated correctly."""
        # Create some invoices with unique numbers
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="BILL-INV-01",
            total_amount=Decimal('1000.00'),
            status='PAID',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        Invoice.objects.create(
            user=self.user,
            client=self.client_obj,
            number="BILL-INV-02",
            total_amount=Decimal('500.00'),
            status='PENDING',
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30)
        )
        
        response = self.client.get('/invoices/')
        self.assertEqual(response.status_code, 200)
        
        total_billed = response.context['total_billed']
        # 1000 + 500 = 1500
        self.assertEqual(total_billed, Decimal('1500.00'))
        print(f"✓ Total Billed: R {total_billed}")