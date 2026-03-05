"""Google Calendar integration utilities."""
import os
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from django.conf import settings
from django.utils import timezone as django_timezone

# Allow HTTP for localhost development (remove in production!)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

from .models import GoogleCalendarCredential, Todo


# Google Calendar API scope
SCOPES = ['https://www.googleapis.com/auth/calendar']


def get_google_calendar_service(user):
    """
    Get an authorized Google Calendar service for the user.
    If token is expired, refreshes it.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        creds_obj = GoogleCalendarCredential.objects.get(user=user)
    except GoogleCalendarCredential.DoesNotExist:
        logger.error(f"No Google Calendar credentials found for {user.username}")
        return None
    
    # Create credentials from stored data
    creds = Credentials(
        token=creds_obj.access_token,
        refresh_token=creds_obj.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=SCOPES
    )
    
    # Check if token is expired and refresh if needed
    if creds_obj.is_token_expired():
        logger.warning(f"Token expired for {user.username}, attempting refresh")
        if not creds_obj.refresh_token:
            logger.error(f"No refresh token available for {user.username}. User needs to reconnect Google Calendar.")
            return None
        
        try:
            creds.refresh(Request())
            # Update the stored credentials
            creds_obj.access_token = creds.token
            if creds.refresh_token:
                creds_obj.refresh_token = creds.refresh_token
            if creds.expiry:
                creds_obj.token_expiry = creds.expiry.replace(tzinfo=timezone.utc)
            creds_obj.save()
            logger.info(f"Successfully refreshed token for {user.username}")
        except Exception as e:
            logger.exception(f"Error refreshing token for {user.username}: {e}")
            return None
    
    return build('calendar', 'v3', credentials=creds)


def get_oauth_flow():
    """Create and return Google OAuth flow."""
    from google_auth_oauthlib.flow import Flow
    
    # Build client config from environment variables
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI
    )
    return flow


def sync_todo_to_calendar(user, todo: Todo, service=None):
    """
    Sync a single todo to Google Calendar.
    Creates or updates a calendar event.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not service:
        service = get_google_calendar_service(user)
    
    if not service:
        logger.error(f"No Google Calendar service available for {user.username}")
        return None
    
    try:
        creds_obj = GoogleCalendarCredential.objects.get(user=user)
    except GoogleCalendarCredential.DoesNotExist:
        logger.error(f"No Google Calendar credentials found for {user.username}")
        return None
    
    calendar_id = creds_obj.calendar_id or 'primary'
    
    # Build event data with marker so we can filter them in import view
    todo_title = f"{todo.category.name if todo.category else 'Todo'} - {todo.client.name}" if todo.client else f"{todo.category.name if todo.category else 'Todo'}"
    event = {
        'summary': f"[Synced] {todo_title}",
        'description': todo.description or '',
        'status': 'cancelled' if todo.status == 'cancelled' else 'confirmed',
    }
    
    # Add date if due_date is set
    if todo.due_date:
        event['start'] = {
            'date': todo.due_date.isoformat(),
        }
        event['end'] = {
            'date': (todo.due_date + timedelta(days=1)).isoformat(),
        }
        logger.debug(f"Todo {todo.id} has due date: {todo.due_date}")
    else:
        # If no due date, use today
        today = django_timezone.now().date()
        event['start'] = {
            'date': today.isoformat(),
        }
        event['end'] = {
            'date': (today + timedelta(days=1)).isoformat(),
        }
        logger.debug(f"Todo {todo.id} has no due date, using today: {today}")
    
    # Check if event already exists in calendar
    # For now, create a new event (can enhance with sync tracking)
    try:
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        event_id = created_event.get('id')
        logger.info(f"Created calendar event {event_id} for todo {todo.id}")
        return event_id
    except Exception as e:
        logger.exception(f"Error syncing todo {todo.id} to calendar: {str(e)}")
        return None


def sync_all_todos_to_calendar(user):
    """
    Sync all of a user's todos to Google Calendar.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting calendar sync for user {user.username}")
    
    service = get_google_calendar_service(user)
    if not service:
        logger.error(f"Could not get Google Calendar service for {user.username}")
        return 0
    
    todos = Todo.objects.filter(user=user).exclude(status='cancelled')
    logger.info(f"Found {todos.count()} todos to sync for {user.username}")
    
    synced_count = 0
    
    for todo in todos:
        try:
            if sync_todo_to_calendar(user, todo, service):
                synced_count += 1
                logger.info(f"Synced todo {todo.id}: {todo.description}")
            else:
                logger.warning(f"Failed to sync todo {todo.id}: {todo.description}")
        except Exception as e:
            logger.exception(f"Error syncing todo {todo.id}: {str(e)}")
    
    logger.info(f"Sync complete. Synced {synced_count} todos for {user.username}")
    return synced_count
