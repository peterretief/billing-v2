from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # The # noqa: F401 stops Ruff from deleting this "unused" import
        import core.signals  # noqa: F401