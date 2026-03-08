"""
Celery tasks for Google Calendar integration and event syncing.
"""
from celery import shared_task
from core.models import User
from django.utils import timezone
from datetime import timedelta
from django.db import models
import logging
import json
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_user_events_with_calendar(self, user_id):
    """
    Background task: Sync all of a user's events with Google Calendar.
    Runs periodically (every 5-10 minutes) to detect changes on both sides.
    
    Uses the bidirectional sync with field ownership model:
    - Calendar owns: scheduling (due_date, start_time)
    - App owns: metadata (description, category, status, etc)
    """
    from .models import Event
    from .calendar_utils import sync_event_bidirectional, get_google_calendar_service
    
    try:
        user = User.objects.get(id=user_id)
        
        # Get Google Calendar service
        try:
            service = get_google_calendar_service(user)
        except Exception as e:
            logger.warning(f"Could not get calendar service for user {user_id}: {str(e)}")
            return False
        
        if not service:
            logger.warning(f"No Google Calendar service available for user {user_id}")
            return False
        
        # Find events that need syncing
        # Priority: pending/failed status, or not synced recently (>5 minutes)
        cutoff = timezone.now() - timedelta(minutes=5)
        
        events_to_sync = Event.objects.filter(
            user=user,
            google_calendar_event_id__isnull=False
        ).exclude(
            google_calendar_event_id=''
        ).filter(
            models.Q(sync_status__in=['pending', 'failed']) |
            models.Q(last_synced_at__lt=cutoff) |
            models.Q(last_synced_at__isnull=True)
        ).order_by('-updated_at')[:50]  # Limit to prevent API rate limiting
        
        synced = 0
        failed = 0
        
        logger.info(f"Syncing {events_to_sync.count()} events for user {user.username}")
        
        for event in events_to_sync:
            try:
                if sync_event_bidirectional(user, event, service):
                    synced += 1
                else:
                    failed += 1
            except Exception as e:
                logger.exception(f"Error syncing event {event.id}: {str(e)}")
                failed += 1
        
        logger.info(f"Sync complete for user {user.username}: {synced} succeeded, {failed} failed")
        
        # Send WebSocket notification if sync was successful
        if synced > 0:
            try:
                # Get updated events to send as notification
                # Get synced events for display
                synced_events_qs = Event.objects.filter(
                    user=user,
                    sync_status='synced',
                    last_synced_at__gte=timezone.now() - timedelta(seconds=10)
                ).select_related('category')
                
                # Build event data with full timing info
                events_data = []
                for event in synced_events_qs:
                    event_data = {
                        'id': event.id,
                        'category_name': event.category.name if event.category else 'Uncategorized',
                        'due_date': str(event.due_date) if event.due_date else None,
                        'calendar_start_time': event.calendar_start_time.isoformat() if event.calendar_start_time else None,
                        'calendar_end_time': event.calendar_end_time.isoformat() if event.calendar_end_time else None,
                        'suggested_start_time': event.suggested_start_time.isoformat() if event.suggested_start_time else None,
                        'status': event.status,
                        'priority': event.priority,
                    }
                    events_data.append(event_data)
                
                # Send to WebSocket group
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"user_sync_{user.id}",
                    {
                        "type": "sync_update",
                        "message": {
                            "events": events_data,
                            "timestamp": timezone.now().isoformat(),
                            "synced_count": synced,
                            "failed_count": failed,
                        }
                    }
                )
                logger.debug(f"Sent WebSocket notification for {len(events_data)} events to user {user.username}")
            except Exception as e:
                logger.warning(f"Could not send WebSocket notification: {str(e)}")
        
        return True
        
    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found")
        return False
    except Exception as e:
        logger.exception(f"Error in sync task for user {user_id}: {str(e)}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@shared_task
def sync_all_users_events_with_calendar():
    """
    Queue sync tasks for all users with Google Calendar connected.
    To be scheduled via Celery Beat every 5-10 minutes.
    """
    from .models import GoogleCalendarCredential
    
    try:
        # Find all users with Google Calendar credentials
        users_with_cal = GoogleCalendarCredential.objects.values_list('user_id', flat=True)
        
        logger.info(f"Queueing calendar sync for {len(users_with_cal)} users")
        
        for user_id in users_with_cal:
            # Queue task for each user
            sync_user_events_with_calendar.delay(user_id)
        
        return f"Queued sync for {len(users_with_cal)} users"
        
    except Exception as e:
        logger.exception(f"Error queueing user sync tasks: {str(e)}")
        return False


@shared_task
def cleanup_old_sync_logs():
    """
    Clean up old sync logs to prevent table bloat.
    Keep logs from last 90 days.
    To be scheduled via Celery Beat (weekly or daily).
    """
    from .models import EventSyncLog
    
    try:
        cutoff_date = timezone.now() - timedelta(days=90)
        deleted_count, _ = EventSyncLog.objects.filter(created_at__lt=cutoff_date).delete()
        
        logger.info(f"Cleaned up {deleted_count} old sync logs")
        return f"Deleted {deleted_count} old sync logs"
        
    except Exception as e:
        logger.exception(f"Error cleaning up sync logs: {str(e)}")
        return False
