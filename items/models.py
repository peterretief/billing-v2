from django.db import models
from django.utils import timezone

from clients.models import Client
from core.models import TenantModel

from .managers import ItemManager


class Item(TenantModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='items')
    description = models.TextField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.now)
    is_billed = models.BooleanField(default=False)
    is_taxable = models.BooleanField(default=False)
   
    # This is the "Billed" state: Null until the invoice is generated
    invoice = models.ForeignKey(
        'invoices.Invoice', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='billed_items' # Mirroring your 'billed_timesheets' pattern
    )
    objects = ItemManager()

    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Items"

    is_recurring = models.BooleanField(
        default=False, 
        help_text="If checked, this item will be automatically billed every month."
    )

    last_billed_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.date} - {self.client.name} - {self.description} \
            (Recurring: {self.is_recurring})"

    @property
    def total(self):
        return self.quantity * self.unit_price


