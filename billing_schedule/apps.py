from django.apps import AppConfig


class BillingScheduleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing_schedule"

    def ready(self):
        # This import MUST be inside the ready() method to avoid circular imports
        import billing_schedule.signals
