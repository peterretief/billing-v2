import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from django.conf import settings
from django.utils import timezone
from ...models import GoogleCalendarCredential

logger = logging.getLogger(__name__)

class GoogleClient:
    """Base client for Google API interactions."""
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self, user):
        self.user = user
        self.creds_obj = None
        self._load_credentials()

    def _load_credentials(self):
        try:
            self.creds_obj = GoogleCalendarCredential.objects.get(user=self.user)
        except GoogleCalendarCredential.DoesNotExist:
            self.creds_obj = None

    def get_service(self, service_name='calendar', version='v3'):
        """Builds and returns an authorized Google API service."""
        if not self.creds_obj:
            return None

        creds = Credentials(
            token=self.creds_obj.access_token,
            refresh_token=self.creds_obj.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=self.SCOPES
        )

        if self.creds_obj.is_token_expired():
            if not self.creds_obj.refresh_token:
                logger.error(f"No refresh token for {self.user.username}")
                return None
            
            try:
                creds.refresh(Request())
                self.creds_obj.access_token = creds.token
                if creds.refresh_token:
                    self.creds_obj.refresh_token = creds.refresh_token
                if creds.expiry:
                    self.creds_obj.token_expiry = creds.expiry.replace(tzinfo=timezone.utc)
                self.creds_obj.save()
            except Exception as e:
                logger.exception(f"Failed to refresh token: {e}")
                return None

        return build(service_name, version, credentials=creds)
