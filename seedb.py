import os
from decimal import Decimal

import django
from django.utils import timezone

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_project.settings")
django.setup()

from clients.models import Client
from core.models import User
from invoices.models import Invoice
from items.models import Item
from timesheets.models import TimesheetEntry, WorkCategory


def seed_data():
    # 1. Create User
    user, created = User.objects.get_or_create(username="peter_test", email="peter@example.com")
    user.set_password("password123")
    user.save()

    # 2. Update Profile
    profile = user.profile
    profile.company_name = "Peter's Consulting"
    profile.vat_rate = Decimal("15.00")
    profile.save()

    # 3. Create Client
    client = Client.objects.create(
        user=user, name="Acme Corp", email="finance@acme.com", address="123 Innovation Drive"
    )

    # 4. Create Work Category
    cat = WorkCategory.objects.create(user=user, name="Development")

    # 5. Create an Invoice (Draft)
    invoice = Invoice.objects.create(
        user=user,
        client=client,
        number="INV-2026-001",
        due_date=timezone.now().date() + timezone.timedelta(days=14),
    )

    # 6. Add a Line Item
    Item.objects.create(
        user=user,
        client=client,
        invoice=invoice,
        description="Server Migration",
        unit_price=Decimal("5000.00"),
        quantity=1,
        is_billed=True,
    )

    # 7. Add a Timesheet Entry
    TimesheetEntry.objects.create(
        user=user,
        client=client,
        invoice=invoice,
        category=cat,
        description="API Integration Work",
        hours=Decimal("10.5"),
        hourly_rate=Decimal("850.00"),
        is_billed=True,
    )

    # 8. Sync and Save
    invoice.sync_totals()
    invoice.save()

    print(f"Success! Created Invoice {invoice.number} for {client.name}")
    print(f"Total Amount: R {invoice.total_amount}")


if __name__ == "__main__":
    seed_data()
