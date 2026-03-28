"""
Script to fix invoice-item links and find problematic invoices.

Usage:
    python manage.py shell < scripts/fix_invoice_links.py
"""
from invoices.models import Invoice
from items.models import Item
from django.db.models import Q

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../')

# 2. Find all non-draft, non-cancelled invoices with total 0
problem_invoices = Invoice.objects.filter(~Q(status__in=[Invoice.Status.DRAFT, Invoice.Status.CANCELLED]), total_amount=0)
print(f"\nInvoices with status SENT/PAID/OVERDUE and total 0:")
for inv in problem_invoices:
    print(f"  Invoice: {inv.number}, Status: {inv.status}, Client: {inv.client}, Issued: {inv.date_issued}, ID: {inv.id}")
    print(f"    Items: {inv.billed_items.count()}, Timesheets: {getattr(inv, 'billed_timesheets', []).count() if hasattr(inv, 'billed_timesheets') else 'N/A'}")

# 3. Delete all invoices with total_amount=0 (any status)
zero_total_invoices = Invoice.objects.filter(total_amount=0)
print(f"\nDeleting {zero_total_invoices.count()} invoices with total_amount=0...")
for inv in zero_total_invoices:
    print(f"  Deleting Invoice: {inv.number}, Status: {inv.status}, Client: {inv.client}, Issued: {inv.date_issued}, ID: {inv.id}")
    inv.delete()
print("Deletion complete.")
