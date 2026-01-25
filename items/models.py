from django.db import models
from django.utils import timezone
from core.models import TenantModel
from clients.models import Client
from invoices.models import Invoice

from .managers import ItemManager

class Item(TenantModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='items')
    description = models.TextField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.now)
    is_billed = models.BooleanField(default=False)
    invoice = models.ForeignKey(
        'invoices.Invoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='billed_items'
    )

    objects = ItemManager()

    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Items"

    def __str__(self):
        return f"{self.date} - {self.client.name} - {self.description}"

    @property
    def total(self):
        return self.quantity * self.unit_price