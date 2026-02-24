import re
from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce

from core.models import TenantModel


class ClientQuerySet(models.QuerySet):
    def with_balances(self):
        """This makes .with_balances() available on the QuerySet"""
        return self.annotate(
            unpaid_total=Coalesce(
                Sum("invoices__total_amount", filter=Q(invoices__status__in=["DRAFT", "PENDING", "OVERDUE"])),
                Decimal("0.00"),
                output_field=DecimalField(),
            )
        )


class Client(TenantModel):
    """
    Client model inheriting from TenantModel.
    Automatically includes user, created_at, and updated_at.

    """

    payment_terms = models.PositiveIntegerField(default=14, help_text="Days until invoice is due")
    default_hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, help_text="Standard rate used for new timesheet entries."
    )
    objects = ClientQuerySet.as_manager()
    name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True, verbose_name="Contact Name")
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    vat_number = models.CharField(max_length=50, blank=True, verbose_name="VAT Number")
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="TAX Number")
    vendor_number = models.CharField(max_length=50, blank=True, verbose_name="Vendor Number")

    client_code = models.CharField(max_length=10, blank=True)

    weekly_target_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00, help_text="Target hours per week for this client."
    )
    monthly_target_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=0.00, help_text="Target hours per month for this client."
    )

    def save(self, *args, **kwargs):
        if not self.client_code:
            # 1. Strip non-alphanumeric characters (e.g., "A&B Corp" -> "ABC")
            clean_name = re.sub(r"\W+", "", self.name).upper()
            # 2. Take the first 4 characters
            base_code = clean_name[:4]
            # 3. If the name is very short, pad it
            self.client_code = base_code.ljust(3, "X")

        super().save(*args, **kwargs)

    @property
    def salutation(self):
        """Returns contact name if available, otherwise company name."""
        return self.contact_name if self.contact_name else self.name

    def __str__(self):
        return self.salutation

    class Meta:
        ordering = ["name"]  # Moved outside the constraints list
        constraints = [models.UniqueConstraint(fields=["user", "client_code"], name="unique_client_code_per_user")]
