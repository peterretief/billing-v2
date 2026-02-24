from django.db import models
from django.utils import timezone

from clients.models import Client
from core.models import TenantModel

from .managers import ItemManager


class ServiceItem(TenantModel):
    description = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    billing_policy = models.ForeignKey(
        "billing_schedule.BillingPolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_items",  # Unique name
    )

    is_recurring = models.BooleanField(default=False)
    last_billed_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.description} ({self.user.username})"


class Item(TenantModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="items")
    description = models.TextField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.now)
    is_billed = models.BooleanField(default=False)
    is_taxable = models.BooleanField(default=False)

    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="billed_items"
    )

    # Scheduling Fields
    billing_policy = models.ForeignKey(
        "billing_schedule.BillingPolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_items",  # Unique name
        help_text="Choose the schedule this item follows.",
    )

    is_recurring = models.BooleanField(
        default=False, help_text="If checked, this item will be automatically billed every month."
    )

    last_billed_date = models.DateField(null=True, blank=True)

    objects = ItemManager()

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Items"

    def __str__(self):
        return f"{self.date} - {self.client.name} - {self.description[:30]}... (Recurring: {self.is_recurring})"

    @property
    def total(self):
        # Ensure we return a decimal even if values are missing
        return (self.quantity or 0) * (self.unit_price or 0)

    @property
    def row_subtotal(self):
        # Alias for total for backward compatibility with templates
        return self.total
