from django.apps import AppConfig

class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'
    verbose_name = "Inventory"
    
    # Plugin metadata
    is_plugin = True
    plugin_display_name = "Inventory"
    plugin_description = "Track stock levels, warehouse locations, and inventory value."
