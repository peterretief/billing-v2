from django.apps import AppConfig

class TimesheetsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'timesheets'
    verbose_name = "Timesheets"
    
    # Plugin metadata
    is_plugin = True
    plugin_display_name = "Timesheets"
    plugin_description = "Track billable hours and generate invoices."
