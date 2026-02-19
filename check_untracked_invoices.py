
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_project.settings')
django.setup()

from invoices.models import Invoice, InvoiceEmailStatusLog


def find_untracked_invoices():
    """
    Finds invoices with a 'PENDING' status that do not have an associated
    InvoiceEmailStatusLog record.
    """
    untracked_invoices = Invoice.objects.filter(
        status=Invoice.Status.PENDING
    ).exclude(
        pk__in=InvoiceEmailStatusLog.objects.values('invoice_id')
    )
    
    if untracked_invoices.exists():
        print("Found untracked invoices:")
        for invoice in untracked_invoices:
            print(f"  - Invoice #{invoice.number} for client {invoice.client.name}")
    else:
        print("No untracked invoices found.")

if __name__ == '__main__':
    find_untracked_invoices()
