from django.db import models
from django.utils import timezone
from core.models import TenantModel

class GoogleCalendarCredential(TenantModel):
    """Bridge model: Stores OAuth credentials for Google Calendar."""
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    sync_enabled = models.BooleanField(default=True)
    calendar_id = models.CharField(max_length=255, blank=True, null=True)
    email_address = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Calendar Credential"
        verbose_name_plural = "Google Calendar Credentials"
        unique_together = ('user',)

    def is_token_expired(self):
        return self.token_expiry and timezone.now() >= self.token_expiry

class BrevoSender(TenantModel):
    """Bridge model: Tracks verified Brevo senders per tenant."""
    sender_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} <{self.email}>"

class ItemInventoryLink(TenantModel):
    """
    Bridge table: Links a billing 'Item' to a physical 'InventoryItem'.
    This allows the system to decrement stock when an item is invoiced
    without the 'items' app knowing about the 'inventory' app.
    """
    # Using string references to avoid circular imports and maintain independence
    item = models.ForeignKey("items.Item", on_delete=models.CASCADE, related_name="inventory_links")
    inventory_item = models.ForeignKey("inventory.InventoryItem", on_delete=models.CASCADE, related_name="item_links")
    
    # How many inventory units are used for 1 billing item
    # e.g., Billing 1 "Six Pack" might decrement 6 "Bottles" in inventory
    quantity_multiplier = models.DecimalField(max_digits=10, decimal_places=2, default=1.0)
    
    auto_decrement = models.BooleanField(
        default=True, 
        help_text="Automatically reduce stock when this item is billed"
    )

    class Meta:
        verbose_name = "Item Inventory Link"
        unique_together = ('item', 'inventory_item')

    def __str__(self):
        return f"{self.item.name} <-> {self.inventory_item.sku}"

class IntegrationSettings(TenantModel):
    """
    Central settings for toggling modules/features for a tenant.
    Items is enabled by default as requested.
    """
    items_enabled = models.BooleanField(default=True, help_text="Billing items module")
    inventory_enabled = models.BooleanField(default=False, help_text="Inventory linked items")
    timesheets_enabled = models.BooleanField(default=False, help_text="Billable timesheets")
    calendar_events_enabled = models.BooleanField(default=False, help_text="Google Calendar Sync")

    class Meta:
        verbose_name = "Integration Setting"
        verbose_name_plural = "Integration Settings"

    def __str__(self):
        return f"Integration Settings for {self.user.email}"
