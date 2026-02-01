from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from core.models import UserProfile
from invoices.models import Invoice
from invoices.utils import email_invoice_to_client
from items.models import Item
from items.services import import_recurring_to_invoices


class RecurringInvoicingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='recurring_test', email='rtest@example.com', password='pw')
        # Ensure profile exists (invoice utils expects it)
        UserProfile.objects.create(user=self.user, company_name='TestCo', business_email='biz@testco.example')

    @patch('invoices.utils.generate_invoice_pdf')
    @patch('django.core.mail.EmailMessage.send')
    def test_import_recurring_creates_invoice_and_emails(self, mock_send, mock_generate_pdf):
        """
        End-to-end test: create a historical billed invoice with a recurring item,
        run the import, then ensure the new invoice is created and emailing works.
        """
        mock_generate_pdf.return_value = b"%PDF-1.4-test"
        mock_send.return_value = 1

        # Create a client and a historical invoice with a recurring item
        client = Client.objects.create(user=self.user, name='Client A', email='clienta@example.com', payment_terms=14)
        past = (timezone.now() - timedelta(days=40)).date()
        template_inv = Invoice.objects.create(
            user=self.user,
            client=client,
            number='TPL-UT-01',
            date_issued=past,
            due_date=past + timedelta(days=14),
            status=Invoice.Status.PENDING,
        )

        Item.objects.create(
            user=self.user,
            client=client,
            invoice=template_inv,
            description='Recurring service',
            quantity=1,
            unit_price=Decimal('100.00'),
            is_recurring=True,
            is_taxable=True,
        )

        # Run the import function
        created_ids = import_recurring_to_invoices(self.user)
        self.assertTrue(len(created_ids) >= 1, 'No invoices created for recurring items')

        # Email each generated invoice (this will hit mocked PDF/email)
        for pk in created_ids:
            inv = Invoice.objects.get(pk=pk)
            result = email_invoice_to_client(inv)
            self.assertTrue(result)

        # Ensure PDF generation and email send were called at least once
        self.assertTrue(mock_generate_pdf.called)
        self.assertTrue(mock_send.called)
