from django.apps import AppConfig

class ItemsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'items'

    def ready(self):
        # The # noqa: F401 stops Ruff from deleting this "unused" import
        import items.signals  # noqa: F401