from django.apps import AppConfig


class InvoicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "invoices"

    def ready(self):
        # The # noqa: F401 stops Ruff from deleting this "unused" import
        import invoices.signals  # noqa: F401
