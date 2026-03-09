from django.apps import AppConfig


class ClientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "clients"

    def ready(self):
        # The # noqa: F401 stops Ruff from deleting this "unused" import
        import clients.signals  # noqa: F401
        import clients.tasks  # noqa: F401
