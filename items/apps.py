from django.apps import AppConfig

class ItemsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'items'
    verbose_name = "Items"
    
    # Plugin metadata
    is_plugin = True
    plugin_display_name = "Items"
    plugin_description = "Manage and invoice fixed-price items."
