import sib_api_v3_sdk
from django.conf import settings
from sib_api_v3_sdk.rest import ApiException
from ..base import BaseIntegrationProvider
from ...models import BrevoSender

class BrevoProvider(BaseIntegrationProvider):
    """Provider for Brevo Email services."""
    
    def __init__(self, user=None):
        super().__init__(user)
        self.configuration = sib_api_v3_sdk.Configuration()
        self.configuration.api_key["api-key"] = settings.BREVO_API_KEY
        self.api_instance = sib_api_v3_sdk.AccountApi(sib_api_v3_sdk.ApiClient(self.configuration))

    def is_configured(self):
        return bool(settings.BREVO_API_KEY)

    def create_sender(self, name, email):
        """Register a new sender and track it in our model."""
        sender_data = sib_api_v3_sdk.CreateSender(name=name, email=email)
        try:
            api_response = self.api_instance.create_sender(sender=sender_data)
            sender_id = api_response.id
            
            # Save to our self-contained model
            sender, created = BrevoSender.objects.get_or_create(
                user=self.user,
                email=email,
                defaults={'name': name, 'sender_id': sender_id}
            )
            return sender
        except ApiException as e:
            self.logger.error(f"Brevo API error: {e}")
            return None
