import logging
from datetime import datetime, timedelta
from .client import GoogleClient

logger = logging.getLogger(__name__)

class GoogleCalendarProvider(GoogleClient):
    """Bridge: Pure logic for talking to Google Calendar API."""
    
    def upsert_event(self, event_data):
        """
        Create or update a calendar event using a dictionary of data.
        Args:
            event_data (dict):
                - google_event_id: (Optional) ID for update
                - summary: Title of the event
                - description: Body text
                - start_time: datetime
                - duration_minutes: int
                - location: (Optional) string
        """
        service = self.get_service()
        if not service: return None
        
        calendar_id = self.creds_obj.calendar_id or 'primary'
        
        start_dt = event_data['start_time']
        end_dt = start_dt + timedelta(minutes=event_data.get('duration_minutes', 60))
        
        body = {
            'summary': event_data['summary'],
            'description': event_data.get('description', ''),
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Africa/Johannesburg'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Africa/Johannesburg'},
        }
        
        if event_data.get('location'):
            body['location'] = event_data['location']

        try:
            if event_data.get('google_event_id'):
                res = service.events().update(calendarId=calendar_id, eventId=event_data['google_event_id'], body=body).execute()
            else:
                res = service.events().insert(calendarId=calendar_id, body=body).execute()
            return res
        except Exception as e:
            logger.exception(f"Google Calendar Bridge Error: {e}")
            return None

    def fetch_events(self, time_min, time_max):
        """Fetch raw event list from Google."""
        service = self.get_service()
        if not service: return []
        
        calendar_id = self.creds_obj.calendar_id or 'primary'
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            return events_result.get('items', [])
        except Exception as e:
            logger.exception(f"Google Calendar Bridge Fetch Error: {e}")
            return []
