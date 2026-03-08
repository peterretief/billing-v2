"""Google Calendar integration utilities."""
import os
import logging
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

from .models import GoogleCalendarCredential, Event, EventSyncLog

logger = logging.getLogger(__name__)


class InvalidScopeError(Exception):
    """Raised when OAuth scope mismatch is detected (usually after new permissions added)."""
    pass


# Google Calendar API scope
SCOPES = [
    'https://www.googleapis.com/auth/calendar'
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


def sync_event_to_calendar(user, todo: Event, service=None):
    """
    Sync a single event to Google Calendar.
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
    todo_title = f"{todo.category.name if todo.category else 'Event'} - {todo.client.name}" if todo.client else f"{todo.category.name if todo.category else 'Event'}"
    
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
    
    # Add date/time if due_date is set
    # Create as TIMED events (not all-day) so they're draggable in Google Calendar
    if todo.suggested_start_time:
        # Use the suggested start time from slot finder
        start_datetime = todo.suggested_start_time
        # Calculate end time based on estimated_hours or default to 1 hour
        duration_minutes = int((todo.estimated_hours or 1) * 60) if todo.estimated_hours else 60
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)
        
        event['start'] = {
            'dateTime': start_datetime.isoformat(),
            'timeZone': 'Africa/Johannesburg',
        }
        event['end'] = {
            'dateTime': end_datetime.isoformat(),
            'timeZone': 'Africa/Johannesburg',
        }
        logger.debug(f"Event {todo.id} using suggested time: {start_datetime} - {end_datetime}")
    elif todo.due_date:
        # Set to 9:00 AM on the due date (user can drag to adjust time)
        start_datetime = datetime.combine(todo.due_date, datetime.min.time().replace(hour=9))
        end_datetime = start_datetime.replace(hour=10)  # 1-hour default duration
        
        event['start'] = {
            'dateTime': start_datetime.isoformat(),
            'timeZone': 'Africa/Johannesburg',  # Default timezone, user can adjust
        }
        event['end'] = {
            'dateTime': end_datetime.isoformat(),
            'timeZone': 'Africa/Johannesburg',
        }
        logger.debug(f"Event {todo.id} has due date: {todo.due_date}, creating timed event at 9:00 AM")
    else:
        # If no due date, use today at 2:00 PM
        today = django_timezone.now().date()
        start_datetime = datetime.combine(today, datetime.min.time().replace(hour=14))
        end_datetime = start_datetime.replace(hour=15)
        
        event['start'] = {
            'dateTime': start_datetime.isoformat(),
            'timeZone': 'Africa/Johannesburg',
        }
        event['end'] = {
            'dateTime': end_datetime.isoformat(),
            'timeZone': 'Africa/Johannesburg',
        }
        logger.debug(f"Event {todo.id} has no due date, using today at 2:00 PM: {today}")
    
    # Check if event already exists in calendar
    # For now, create a new event (can enhance with sync tracking)
    try:
        if todo.google_calendar_event_id:
            # Event already synced - update it instead of creating duplicate
            updated_event = service.events().update(
                calendarId=calendar_id,
                eventId=todo.google_calendar_event_id,
                body=event
            ).execute()
            event_id = updated_event.get('id')
            # Also update the calendar times and etag in database
            todo.calendar_start_time = _extract_datetime_from_calendar(updated_event)
            todo.calendar_end_time = _extract_end_datetime_from_calendar(updated_event)
            todo.google_calendar_etag = updated_event.get('etag')
            todo.save(update_fields=['calendar_start_time', 'calendar_end_time', 'google_calendar_etag'])
            logger.info(f"Updated calendar event {event_id} for todo {todo.id}")
        else:
            # New event - create and store the event ID
            created_event = service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
            event_id = created_event.get('id')
            
            # Store the event ID, extracted times, and etag to prevent duplicates on future syncs
            todo.google_calendar_event_id = event_id
            todo.calendar_start_time = _extract_datetime_from_calendar(created_event)
            todo.calendar_end_time = _extract_end_datetime_from_calendar(created_event)
            todo.google_calendar_etag = created_event.get('etag')
            todo.save(update_fields=['google_calendar_event_id', 'calendar_start_time', 'calendar_end_time', 'google_calendar_etag'])
            
            logger.info(f"Created calendar event {event_id} for todo {todo.id}")
        
        return event_id
    except Exception as e:
        logger.exception(f"Error syncing todo {todo.id} to calendar: {str(e)}")
        return None


def sync_all_events_to_calendar(user):
    """
    Sync all of a user's events to Google Calendar.
    Only syncs events that have a due_date set (not backlog items).
    """

    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting calendar sync for user {user.username}")
    
    service = get_google_calendar_service(user)
    if not service:
        logger.error(f"Could not get Google Calendar service for {user.username}")
        return 0
    
    # Only sync todos with due_date set (exclude backlog/undated items)
    todos = Event.objects.filter(user=user).exclude(status='cancelled').filter(due_date__isnull=False)
    logger.info(f"Found {todos.count()} todos with due dates to sync for {user.username}")
    
    synced_count = 0
    
    for todo in todos:
        try:
            if sync_event_to_calendar(user, todo, service):
                synced_count += 1
                # Mark as synced
                todo.synced_to_calendar = True
                todo.save(update_fields=['synced_to_calendar'])
                logger.info(f"Synced todo {todo.id}: {todo.description}")
            else:
                logger.warning(f"Failed to sync todo {todo.id}: {todo.description}")
        except Exception as e:
            logger.exception(f"Error syncing todo {todo.id}: {str(e)}")
    
    logger.info(f"Sync complete. Synced {synced_count} todos for {user.username}")
    return synced_count


def find_available_slots(user, duration_minutes, start_date=None, num_slots=5, days_ahead=30):
    """
    Find available time slots in the user's Google Calendar respecting working hours.
    
    Args:
        user: Django user object
        duration_minutes: How long the event should be (in minutes)
        start_date: Starting date to search from (default: today)
        num_slots: Number of available slots to return (default: 5)
        days_ahead: How many days ahead to search (default: 30)
    
    Returns:
        List of tuples: [(start_datetime, end_datetime), ...]
        Empty list if no slots found or error occurs
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from .models import Event
        from core.models import UserProfile
        
        # Get user's working hours configuration
        try:
            profile = UserProfile.objects.get(user=user)
            work_start_time = profile.work_start_time
            work_end_time = profile.work_end_time
            work_days = profile.get_work_days()  # Returns list of day indices [0-6]
            break_minutes = profile.break_minutes
        except UserProfile.DoesNotExist:
            logger.warning(f"No profile found for {user.username}, using defaults")
            work_start_time = datetime.min.time().replace(hour=9)
            work_end_time = datetime.min.time().replace(hour=17)
            work_days = [0, 1, 2, 3, 4]  # Mon-Fri
            break_minutes = 15
        
        # Set start date to today if not provided
        if start_date is None:
            start_date = django_timezone.now().date()
        
        # Get Google Calendar service
        service = get_google_calendar_service(user)
        if not service:
            logger.error(f"No Google Calendar service for {user.username}")
            return []
        
        try:
            creds_obj = GoogleCalendarCredential.objects.get(user=user)
        except GoogleCalendarCredential.DoesNotExist:
            logger.error(f"No Google Calendar credentials for {user.username}")
            return []
        
        calendar_id = creds_obj.calendar_id or 'primary'
        
        # Query Google Calendar for events
        search_start = datetime.combine(start_date, datetime.min.time())
        search_end = datetime.combine(start_date + timedelta(days=days_ahead), datetime.max.time())
        
        # Convert to ISO format with timezone for API query
        tz = django_timezone.get_current_timezone()
        search_start_iso = django_timezone.make_aware(search_start, tz).isoformat()
        search_end_iso = django_timezone.make_aware(search_end, tz).isoformat()
        
        logger.info(f"Querying calendar for {user.username} from {search_start_iso} to {search_end_iso}")
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=search_start_iso,
            timeMax=search_end_iso,
            singleEvents=True,
            orderBy='startTime',
            showDeleted=False
        ).execute()
        
        events = events_result.get('items', [])
        logger.info(f"Found {len(events)} calendar events for {user.username}")
        
        # Build list of occupied time slots
        occupied_slots = []
        
        # First, add events from Google Calendar
        for event in events:
            # Skip all-day events
            if 'dateTime' not in event.get('start', {}):
                continue
            
            start_str = event['start'].get('dateTime')
            end_str = event['end'].get('dateTime')
            
            if start_str and end_str:
                try:
                    # Parse ISO format datetimes
                    start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                    occupied_slots.append((start_dt, end_dt))
                except ValueError:
                    logger.warning(f"Could not parse event dates: {start_str}, {end_str}")
        
        # Also add events from the app database that haven't been synced yet
        # This prevents duplicate bookings if events are created faster than they sync to Google Calendar
        
        # Include events with suggested_start_time (already have specific times picked)
        app_events_with_time = Event.objects.filter(
            user=user,
            suggested_start_time__isnull=False,
            suggested_start_time__gte=search_start,
            suggested_start_time__lt=search_end
        ).exclude(status='cancelled')
        
        # Also include events with just due_date set (assume full day busy during business hours)
        app_events_with_date = Event.objects.filter(
            user=user,
            due_date__isnull=False,
            due_date__gte=search_start.date(),
            due_date__lt=search_end.date()
        ).exclude(status='cancelled').exclude(suggested_start_time__isnull=False)  # Don't double-count
        
        # Convert time-based events to slots
        for app_event in app_events_with_time:
            try:
                # Calculate end time from suggested_start_time and duration
                start_dt = app_event.suggested_start_time
                if app_event.estimated_hours:
                    # Convert Decimal to float if necessary
                    hours = float(app_event.estimated_hours)
                    duration = timedelta(hours=hours)
                else:
                    duration = timedelta(hours=1)  # Default to 1 hour if no duration specified
                end_dt = start_dt + duration
                occupied_slots.append((start_dt, end_dt))
                logger.debug(f"Added app event {app_event.id} (with time) to occupied slots: {start_dt} - {end_dt}")
            except Exception as e:
                logger.warning(f"Could not add app event {app_event.id} to occupied slots: {str(e)}")
        
        # Convert date-only events to slots (assume they block entire working day)
        for app_event in app_events_with_date:
            try:
                event_date = app_event.due_date
                day_start = django_timezone.make_aware(
                    datetime.combine(event_date, work_start_time),
                    django_timezone.get_current_timezone()
                )
                day_end = django_timezone.make_aware(
                    datetime.combine(event_date, work_end_time),
                    django_timezone.get_current_timezone()
                )
                occupied_slots.append((day_start, day_end))
                logger.debug(f"Added app event {app_event.id} (date only) to occupied slots: {day_start} - {day_end}")
            except Exception as e:
                logger.warning(f"Could not add app event {app_event.id} to occupied slots: {str(e)}")
        
        # Sort occupied slots
        occupied_slots.sort(key=lambda x: x[0])
        logger.info(f"Found {len(occupied_slots)} occupied time slots ({len(events)} from calendar, {app_events_with_time.count()} with time + {app_events_with_date.count()} with date)")
        
        # Find available slots
        available_slots = []
        current_date = start_date
        search_until_date = start_date + timedelta(days=days_ahead)
        
        work_start_seconds = work_start_time.hour * 3600 + work_start_time.minute * 60
        work_end_seconds = work_end_time.hour * 3600 + work_end_time.minute * 60
        total_slot_duration = duration_minutes + break_minutes
        
        while len(available_slots) < num_slots and current_date < search_until_date:
            # Skip days not in work_days list
            if current_date.weekday() not in work_days:
                current_date += timedelta(days=1)
                continue
            
            # Build the working hours window for this day
            day_start = django_timezone.make_aware(
                datetime.combine(current_date, work_start_time),
                django_timezone.get_current_timezone()
            )
            day_end = django_timezone.make_aware(
                datetime.combine(current_date, work_end_time),
                django_timezone.get_current_timezone()
            )
            
            # Find gaps during this working day
            current_time = day_start
            
            for occupied_start, occupied_end in occupied_slots:
                # Check if occupied slot overlaps with this working day
                if occupied_end <= day_start or occupied_start >= day_end:
                    continue
                
                # Ensure occupied times are within the day
                occupied_start = max(occupied_start, day_start)
                occupied_end = min(occupied_end, day_end)
                
                # Check if there's a gap before this occupied slot
                gap_duration = (occupied_start - current_time).total_seconds() / 60
                
                if gap_duration >= total_slot_duration:
                    # We have a gap that fits the duration
                    slot_end = current_time + timedelta(minutes=duration_minutes)
                    available_slots.append((current_time, slot_end))
                    logger.info(f"Found available slot: {current_time} - {slot_end}")
                    
                    if len(available_slots) >= num_slots:
                        return available_slots
                
                # Move to after this occupied slot
                current_time = occupied_end + timedelta(minutes=break_minutes)
            
            # Check for gap at the end of the working day
            remaining_time = (day_end - current_time).total_seconds() / 60
            
            if remaining_time >= total_slot_duration:
                slot_end = current_time + timedelta(minutes=duration_minutes)
                available_slots.append((current_time, slot_end))
                logger.info(f"Found available slot at end of day: {current_time} - {slot_end}")
                
                if len(available_slots) >= num_slots:
                    return available_slots
            
            current_date += timedelta(days=1)
        
        logger.info(f"Found {len(available_slots)} available slots for {user.username}")
        return available_slots
        
    except Exception as e:
        logger.exception(f"Error finding available slots for {user.username}: {str(e)}")
        return []


# ============================================================================
# BIDIRECTIONAL SYNC - Field Ownership Model
# ============================================================================
# Calendar OWNS: due_date, suggested_start_time
# App OWNS: description, category, status, priority, estimated_hours
# Strategy: Calendar source for scheduling, App source for metadata
# ============================================================================

def _is_calendar_newer(event, gc_event):
    """Check if Google Calendar version is more recent than app version.
    
    Uses etag comparison (reliable) instead of timestamps (unreliable due to sync timing).
    If etags differ, calendar has been modified since last sync.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Get current calendar etag
    current_cal_etag = gc_event.get('etag')
    if not current_cal_etag:
        logger.warning("Google Calendar event has no etag")
        return False
    
    # Get stored etag from last sync
    stored_etag = event.google_calendar_etag
    
    # If etags differ, the calendar event has been modified
    is_newer = current_cal_etag != stored_etag
    
    if is_newer:
        stored_etag_preview = stored_etag[:10] if stored_etag else 'None'
        logger.info(f"Calendar event {event.id} changed: etag {stored_etag_preview!r} -> {current_cal_etag[:10]!r}")
    else:
        logger.debug(f"Calendar event {event.id} unchanged (etag: {current_cal_etag[:10]!r})")
    
    return is_newer


def _extract_datetime_from_calendar(event_data):
    """Extract start datetime from Google Calendar event (converted to UTC)."""
    try:
        if 'start' not in event_data:
            return None
        
        start_info = event_data['start']
        
        if 'dateTime' in start_info:
            # Timed event - parse and convert to UTC
            dt = datetime.fromisoformat(start_info['dateTime'].replace('Z', '+00:00'))
            # Convert to UTC for stored in database
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            return dt
        elif 'date' in start_info:
            # All-day event—convert to datetime at midnight UTC
            date_obj = datetime.strptime(start_info['date'], '%Y-%m-%d').date()
            return django_timezone.make_aware(datetime.combine(date_obj, datetime.min.time()), timezone.utc)
    except Exception as e:
        logger.warning(f"Could not extract datetime: {str(e)}")
    
    return None


def _extract_end_datetime_from_calendar(event_data):
    """Extract end datetime from Google Calendar event (converted to UTC)."""
    try:
        if 'end' not in event_data:
            return None
        
        end_info = event_data['end']
        
        if 'dateTime' in end_info:
            # Timed event - parse and convert to UTC
            dt = datetime.fromisoformat(end_info['dateTime'].replace('Z', '+00:00'))
            # Convert to UTC for stored in database
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            return dt
        elif 'date' in end_info:
            # All-day event—convert to datetime at end of day UTC
            date_obj = datetime.strptime(end_info['date'], '%Y-%m-%d').date()
            # For all-day events, end time is typically the next day at midnight
            return django_timezone.make_aware(datetime.combine(date_obj, datetime.min.time()), timezone.utc)
    except Exception as e:
        logger.warning(f"Could not extract end datetime: {str(e)}")
    
    return None


def _extract_date_from_calendar(event_data):
    """Extract start date from Google Calendar event."""
    try:
        dt = _extract_datetime_from_calendar(event_data)
        return dt.date() if dt else None
    except:
        return None


def _update_event_from_calendar(event, gc_event):
    """
    Pull scheduling changes FROM Google Calendar into app.
    Only updates calendar-owned fields.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    changes = {}
    
    # Update due_date from calendar start time
    new_due_date = _extract_date_from_calendar(gc_event)
    if new_due_date and new_due_date != event.due_date:
        changes['due_date'] = {
            'from': str(event.due_date) if event.due_date else None,
            'to': str(new_due_date),
        }
        event.due_date = new_due_date
    
    # Update suggested_start_time from calendar
    new_start_time = _extract_datetime_from_calendar(gc_event)
    if new_start_time and new_start_time != event.suggested_start_time:
        changes['suggested_start_time'] = {
            'from': event.suggested_start_time.isoformat() if event.suggested_start_time else None,
            'to': new_start_time.isoformat(),
        }
        event.suggested_start_time = new_start_time
    
    # Store calendar start and end times (read-only, for display)
    new_calendar_start = _extract_datetime_from_calendar(gc_event)
    if new_calendar_start and new_calendar_start != event.calendar_start_time:
        event.calendar_start_time = new_calendar_start
    
    new_calendar_end = _extract_end_datetime_from_calendar(gc_event)
    if new_calendar_end and new_calendar_end != event.calendar_end_time:
        event.calendar_end_time = new_calendar_end
    
    return changes


def _sync_metadata_to_calendar(user, event, service=None):
    """
    Push app metadata TO Google Calendar.
    Only updates fields that app owns (description, etc).
    Calendar event's due_date/time are preserved.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not event.google_calendar_event_id:
        return None
    
    if not service:
        service = get_google_calendar_service(user)
    if not service:
        return None
    
    try:
        creds_obj = GoogleCalendarCredential.objects.get(user=user)
        calendar_id = creds_obj.calendar_id or 'primary'
        
        # Fetch current calendar event
        gc_event = service.events().get(
            calendarId=calendar_id,
            eventId=event.google_calendar_event_id
        ).execute()
        
        # Build update with app metadata (preserving calendar's date/time)
        update_data = {
            'description': event.description or '',
            'summary': f"{event.category.name if event.category else 'Event'} - {event.client.name}" if event.client else f"{event.category.name if event.category else 'Event'}",
            'status': 'cancelled' if event.status == 'cancelled' else 'confirmed',
        }
        
        # PRESERVE the calendar event's start and end times (required by Google API)
        if 'start' in gc_event:
            update_data['start'] = gc_event['start']
        if 'end' in gc_event:
            update_data['end'] = gc_event['end']
        
        # Add client location if available
        if event.client and event.client.address:
            update_data['location'] = event.client.address
        
        # Update the event (preserving start/end times from calendar)
        service.events().update(
            calendarId=calendar_id,
            eventId=event.google_calendar_event_id,
            body=update_data
        ).execute()
        
        logger.info(f"Updated metadata for calendar event {event.google_calendar_event_id}")
        return True
        
    except Exception as e:
        logger.exception(f"Error syncing metadata for event {event.id}: {str(e)}")
        return False


def sync_event_bidirectional(user, event, service=None):
    """
    Sync an event bidirectionally with clear field ownership.
    
    Strategy:
    - Calendar OWNS: scheduling (due_date, start_time)
    - App OWNS: metadata (description, category, status, priority, estimated_hours)
    - Sync scheduling FROM calendar, metadata TO calendar
    - No merging needed—different systems own different fields
    """
    from .models import EventSyncLog
    
    # New event—just sync app → calendar
    if not event.google_calendar_event_id:
        result = sync_event_to_calendar(user, event, service)
        if result:
            event.sync_status = 'synced'
            event.last_synced_from = 'app'
            event.last_synced_at = django_timezone.now()
            event.save(update_fields=['sync_status', 'last_synced_from', 'last_synced_at'])
        return result
    
    # Existing event—bidirectional sync
    if not service:
        service = get_google_calendar_service(user)
    
    try:
        creds_obj = GoogleCalendarCredential.objects.get(user=user)
        calendar_id = creds_obj.calendar_id or 'primary'
        
        # Fetch calendar version
        gc_event = service.events().get(
            calendarId=calendar_id,
            eventId=event.google_calendar_event_id
        ).execute()
        
        current_etag = gc_event.get('etag')
        
        # Track changes
        all_changes = {}
        
        # Pull scheduling changes FROM calendar if it's newer
        if _is_calendar_newer(event, gc_event):
            logger.info(f"Calendar version is newer for event {event.id}, pulling changes")
            calendar_changes = _update_event_from_calendar(event, gc_event)
            if calendar_changes:
                all_changes.update(calendar_changes)
                event.last_synced_from = 'calendar'
        else:
            # Push app metadata TO calendar
            logger.info(f"App version is current for event {event.id}, pushing metadata")
            metadata_sync_result = _sync_metadata_to_calendar(user, event, service)
            if not metadata_sync_result:
                # Metadata sync failed, mark event as failed
                event.sync_status = 'failed'
                event.last_synced_at = django_timezone.now()
                event.save(update_fields=['sync_status', 'last_synced_at'])
                
                EventSyncLog.objects.create(
                    event=event,
                    sync_direction='push',
                    status='error',
                    error_message='Metadata sync to calendar failed',
                )
                return False
            event.last_synced_from = 'app'
        
        # Update sync metadata (only if we get here - both operations succeeded)
        event.sync_status = 'synced'
        event.last_synced_at = django_timezone.now()
        event.google_calendar_etag = current_etag
        event.save()
        
        # Log the sync operation
        if all_changes:
            EventSyncLog.objects.create(
                event=event,
                sync_direction='pull' if event.last_synced_from == 'calendar' else 'push',
                status='success',
                synced_fields=list(all_changes.keys()),
                changes=all_changes,
            )
        
        logger.info(f"Successfully synced event {event.id}")
        return True
        
    except GoogleCalendarCredential.DoesNotExist:
        logger.error(f"No Google Calendar credentials for user {user.username}")
        return False
    except Exception as e:
        logger.exception(f"Error syncing event {event.id}: {str(e)}")
        event.sync_status = 'failed'
        event.save(update_fields=['sync_status'])
        
        EventSyncLog.objects.create(
            event=event,
            sync_direction='push',
            status='error',
            error_message=str(e),
        )
        return False
