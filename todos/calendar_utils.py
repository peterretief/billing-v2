"""Google Calendar integration utilities."""
import os
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from django.conf import settings
from django.utils import timezone as django_timezone

# Allow HTTP for localhost development (remove in production!)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

from .models import GoogleCalendarCredential, Todo


class InvalidScopeError(Exception):
    """Raised when OAuth scope mismatch is detected (usually after new permissions added)."""
    pass


# Google Calendar and Contacts API scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/contacts'  # For address book sync
]


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
        except RefreshError as e:
            error_str = str(e)
            # Check if it's a scope mismatch error (usually happens when new permissions are added)
            if 'invalid_scope' in error_str:
                logger.warning(f"Scope mismatch for {user.username}. New permissions added. Clearing credentials for re-auth.")
                # Delete the credential to force re-authentication with new scopes
                creds_obj.delete()
                raise InvalidScopeError("Google permissions were updated. Please reconnect your Google account.")
            logger.exception(f"Error refreshing token for {user.username}: {e}")
            return None
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
    
    # Build description with client details if available
    description_parts = []
    if todo.description:
        description_parts.append(todo.description)
    
    # Add client contact information to description
    if todo.client:
        client_info = f"\n\n--- CLIENT DETAILS ---\nName: {todo.client.name}"
        if todo.client.contact_name:
            client_info += f"\nContact: {todo.client.contact_name}"
        if todo.client.phone:
            client_info += f"\nPhone: {todo.client.phone}"
        if todo.client.email:
            client_info += f"\nEmail: {todo.client.email}"
        description_parts.append(client_info)
    
    event = {
        'summary': f"[Synced] {todo_title}",
        'description': ''.join(description_parts),
        'status': 'cancelled' if todo.status == 'cancelled' else 'confirmed',
    }
    
    # Add client address as location (enables Google Maps integration)
    if todo.client and todo.client.address:
        event['location'] = todo.client.address
    
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


def get_google_contacts_service(user):
    """
    Get an authorized Google Contacts (People) API service for the user.
    Shares credentials with calendar service.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        creds_obj = GoogleCalendarCredential.objects.get(user=user)
    except GoogleCalendarCredential.DoesNotExist:
        logger.error(f"No Google credentials found for {user.username}")
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
            logger.error(f"No refresh token available for {user.username}")
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
        except RefreshError as e:
            error_str = str(e)
            # Check if it's a scope mismatch error (usually happens when new permissions are added)
            if 'invalid_scope' in error_str:
                logger.warning(f"Scope mismatch for {user.username}. New permissions added. Clearing credentials for re-auth.")
                # Delete the credential to force re-authentication with new scopes
                creds_obj.delete()
                raise InvalidScopeError("Google permissions were updated. Please reconnect your Google account.")
            logger.exception(f"Error refreshing token for {user.username}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error refreshing token for {user.username}: {e}")
            return None
    
    return build('people', 'v1', credentials=creds)


def sync_client_to_contacts(user, client, service=None):
    """
    Sync a single client to Google Contacts.
    Creates or updates a contact.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not service:
        service = get_google_contacts_service(user)
    
    if not service:
        logger.error(f"No Google Contacts service available for {user.username}")
        return None
    
    # Build contact data
    names = [{'givenName': client.name.split()[0] if ' ' in client.name else client.name,
              'familyName': ' '.join(client.name.split()[1:]) if ' ' in client.name else '',
              'displayName': client.name}]
    
    contact = {
        'names': names,
    }
    
    # Add email
    if client.email:
        contact['emailAddresses'] = [{'value': client.email, 'type': 'work'}]
    
    # Add phone
    if client.phone:
        contact['phoneNumbers'] = [{'value': client.phone, 'type': 'work'}]
    
    # Add address
    if client.address:
        contact['addresses'] = [{
            'formattedValue': client.address,
            'type': 'work'
        }]
    
    # Add note with VAT/Tax info
    notes_parts = []
    if client.contact_name:
        notes_parts.append(f"Contact: {client.contact_name}")
    if client.vat_number:
        notes_parts.append(f"VAT: {client.vat_number}")
    if client.tax_number:
        notes_parts.append(f"TAX: {client.tax_number}")
    if client.vendor_number:
        notes_parts.append(f"Vendor: {client.vendor_number}")
    
    if notes_parts:
        contact['biographies'] = [{'value': ' | '.join(notes_parts)}]
    
    try:
        # Create contact (upsert - Google will handle duplicates)
        created_contact = service.people().createContact(body=contact).execute()
        contact_id = created_contact.get('resourceName')
        logger.info(f"Created/updated contact for {client.name} (ID: {contact_id})")
        return contact_id
    except Exception as e:
        logger.exception(f"Error syncing client {client.id} ({client.name}) to contacts: {str(e)}")
        return None


def sync_all_clients_to_contacts(user):
    """
    Sync all of a user's clients to Google Contacts.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    from clients.models import Client
    
    logger.info(f"Starting contacts sync for user {user.username}")
    
    service = get_google_contacts_service(user)
    if not service:
        logger.error(f"Could not get Google Contacts service for {user.username}")
        return 0
    
    clients = Client.objects.filter(user=user)
    logger.info(f"Found {clients.count()} clients to sync for {user.username}")
    
    synced_count = 0
    
    for client in clients:
        try:
            if sync_client_to_contacts(user, client, service):
                synced_count += 1
                logger.info(f"Synced client {client.id}: {client.name}")
            else:
                logger.warning(f"Failed to sync client {client.id}: {client.name}")
        except Exception as e:
            logger.exception(f"Error syncing client {client.id}: {str(e)}")
    
    logger.info(f"Contacts sync complete. Synced {synced_count} clients for {user.username}")
    return synced_count


def get_google_contacts_list(user, service=None):
    """
    Fetch all contacts from Google Contacts (address book).
    Returns a list of contact dictionaries with name, email, phone, address.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not service:
        service = get_google_contacts_service(user)
    
    if not service:
        logger.error(f"No Google Contacts service available for {user.username}")
        return []
    
    contacts = []
    
    try:
        # Fetch contacts from Google Contacts
        results = service.people().connections().list(
            resourceName='people/me',
            pageSize=1000,
            personFields='names,emailAddresses,phoneNumbers,addresses',
            sortOrder='LAST_MODIFIED_DESCENDING'
        ).execute()
        
        connections = results.get('connections', [])
        logger.info(f"Fetched {len(connections)} contacts from Google Contacts for {user.username}")
        
        for person in connections:
            contact_data = {}
            
            # Get name
            names = person.get('names', [])
            if names:
                contact_data['name'] = names[0].get('displayName', '')
                contact_data['given_name'] = names[0].get('givenName', '')
                contact_data['family_name'] = names[0].get('familyName', '')
            
            # Get email
            emails = person.get('emailAddresses', [])
            if emails:
                contact_data['email'] = emails[0].get('value', '')
            
            # Get phone
            phones = person.get('phoneNumbers', [])
            if phones:
                contact_data['phone'] = phones[0].get('value', '')
            
            # Get address
            addresses = person.get('addresses', [])
            if addresses:
                contact_data['address'] = addresses[0].get('formattedValue', '')
            
            if contact_data.get('name'):
                contacts.append(contact_data)
        
        logger.info(f"Parsed {len(contacts)} contacts for matching")
        return contacts
        
    except Exception as e:
        logger.exception(f"Error fetching Google Contacts for {user.username}: {str(e)}")
        return []
