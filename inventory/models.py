from django.db import models
from core.models import TenantModel

class Warehouse(TenantModel):
    """Physical location where inventory is stored."""
    name = models.CharField(max_length=255)
    location = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class InventoryItem(TenantModel):
    """The physical stock item being tracked."""
    sku = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    unit_of_measure = models.CharField(max_length=50, default="Units") # e.g., kg, liters, boxes
    
    # Stock levels
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Pricing fields
    buy_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sell_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
        unique_together = ('user', 'sku')

    def __str__(self):
        return f"{self.name} ({self.sku})"

class StockTransaction(TenantModel):
    """Audit log for all stock movements."""
    TRANSACTION_TYPES = [
        ('IN', 'Stock In (Purchase/Return)'),
        ('OUT', 'Stock Out (Sale/Usage)'),
        ('ADJ', 'Adjustment (Count/Damage)'),
    ]
    
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='transactions')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_type = models.CharField(max_length=3, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=255, blank=True, help_text="PO number or Invoice reference")
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.inventory_item.name}: {self.quantity}"
