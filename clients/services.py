import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings

class BrevoSenderService:
    def __init__(self):
        # Configure API key from your Django settings
        self.configuration = sib_api_v3_sdk.Configuration()
        self.configuration.api_key['api-key'] = settings.BREVO_API_KEY
        self.api_instance = sib_api_v3_sdk.AccountApi(sib_api_v3_sdk.ApiClient(self.configuration))

    def create_tenant_sender(self, tenant_name, tenant_email):
        """
        Adds a new verified sender to Brevo. 
        Brevo will automatically send a verification email to tenant_email.
        """
        sender_data = sib_api_v3_sdk.CreateSender(
            name=tenant_name,
            email=tenant_email
        )

        try:
            api_response = self.api_instance.create_sender(sender=sender_data)
            # Returns the ID of the new sender
            return api_response.id 
        except ApiException as e:
            print(f"Exception when calling AccountApi->create_sender: {e}")
            return None

    def get_sender_status(self, sender_id):
        """Check if the tenant has verified their email yet."""
        try:
            senders = self.api_instance.get_senders()
            for s in senders.senders:
                if s.id == sender_id:
                    return s.active # True/False
            return False
        except ApiException:
            return False