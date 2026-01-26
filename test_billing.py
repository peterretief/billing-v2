import os
import django
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'billing_v2.settings') # Ensure this matches your project name
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

from invoices.models import Invoice, InvoiceItem
from clients.models import Client

def run_test():
    print("--- Starting Billing Logic Test ---")
    
    # 1. Setup: Get a user and a client
    user = User.objects.first()
    client = Client.objects.first()
    
    if not user or not client:
        print("ERROR: Need at least one User and one Client in the DB to test.")
        return

    # 2. Create an Invoice
    print("Step 1: Creating Invoice...")
    invoice = Invoice.objects.create(
        user=user,
        client=client,
        status='DRAFT',
        due_date=timezone.now() + timedelta(days=30)
    )
    print(f"Created: {invoice.number} (Status: {invoice.status})")

    # 3. Add Line Items
    print("Step 2: Adding Line Items...")
    InvoiceItem.objects.create(
        invoice=invoice,
        description="Consulting",
        quantity=2,
        unit_price=Decimal('150.00')
    )
    InvoiceItem.objects.create(
        invoice=invoice,
        description="Hosting",
        quantity=1,
        unit_price=Decimal('33.00')
    )

    # 4. Final Verification
    invoice.refresh_from_db()
    print(f"Step 3: Verifying Totals...")
    print(f"Subtotal: {invoice.subtotal_amount}")
    print(f"Total Amount: {invoice.total_amount}")

    expected = Decimal('333.00')
    if invoice.total_amount >= expected: # Adjust if you have VAT enabled
        print("SUCCESS: The totals are calculating and persisting!")
    else:
        print(f"FAILURE: Expected at least {expected}, but got {invoice.total_amount}")

if __name__ == "__main__":
    run_test()