import uuid
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

# Adjust these imports based on your actual app names
from clients.models import Client
from invoices.models import Invoice, InvoiceItem
from core.models import UserProfile 

User = get_user_model()

class Command(BaseCommand):
    help = "Seeds the database with tenant-aware test data"

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding data for custom User model...")

        # 1. Create the Custom User
        # Note: REQUIRED_FIELDS includes 'email', so we provide it here
        user, created = User.objects.get_or_create(
            username="peter",
            defaults={
                "email": "peter@diode.co.za",
                "is_staff": True,
                "is_superuser": True,
            }
        )
        if created:
            user.set_password("p3t3rr")
            user.save()
            self.stdout.write(f"Created custom user: {user.username}")

        # 2. Create the UserProfile (Important for VAT/Tax logic)
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "company_name": "Test Solutions Pty Ltd",
                "is_vat_registered": True,
                "vat_rate": Decimal("15.00"),
                "bank_name": "Test Bank",
            }
        )

        # 3. Create a Client linked to this user
        client, _ = Client.objects.get_or_create(
            user=user,
            name="Acme Corp",
            defaults={'email': 'kath@diode.co,za', 'payment_terms': 14}
        )

        # 4. Create dummy Invoices to test sequential numbering
        for i in range(1, 4):
            invoice = Invoice.objects.create(
                user=user,
                client=client,
                number=str(i), # Testing your manual numbering logic
                status=Invoice.Status.DRAFT,
                due_date=timezone.now().date() + timedelta(days=14),
                tax_mode=Invoice.TaxMode.FULL
            )
            
            InvoiceItem.objects.create(
                invoice=invoice,
                description=f"Consulting Services Batch {i}",
                quantity=Decimal("1.0"),
                unit_price=Decimal("1000.00"),
                is_taxable=True
            )
            
            # Sync snapshots so the totals aren't 0.00
            invoice.sync_totals()
            invoice.save()

        self.stdout.write(self.style.SUCCESS("Successfully seeded data for custom tenant user."))