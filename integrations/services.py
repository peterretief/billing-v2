from .providers.google.calendar import GoogleCalendarProvider
from .providers.brevo.client import BrevoProvider
from .providers.gemini.client import GeminiProvider

class IntegrationService:
    """Unified entry point for all external integrations."""
    
    @staticmethod
    def get_calendar(user):
        return GoogleCalendarProvider(user)
    
    @staticmethod
    def get_email(user=None):
        return BrevoProvider(user)
    
    @staticmethod
    def get_ai(user=None):
        return GeminiProvider(user)
