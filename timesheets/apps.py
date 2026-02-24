from django.apps import AppConfig


class TimesheetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "timesheets"

    def ready(self):
        # The # noqa: F401 stops Ruff from deleting this "unused" import
        import timesheets.signals  # noqa: F401
