import logging

class BaseIntegrationProvider:
    """Base class for all external service integrations."""
    
    def __init__(self, user=None):
        self.user = user
        self.logger = logging.getLogger(f"integrations.{self.__class__.__name__}")
    
    def is_configured(self):
        """Check if the integration is properly configured for the user/system."""
        raise NotImplementedError("Subclasses must implement is_configured()")
