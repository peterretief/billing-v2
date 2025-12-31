from django.apps import AppConfig


class InvoicesConfig(AppConfig):
    name = 'invoices'


    def ready(self):
        # This imports the signals when the app starts up
        import invoices.signals