"""
Calendar events completion detection and auto-completion.

This task runs periodically (every 15 minutes) to check if calendar events
have finished and auto-mark the corresponding app events as completed.

Add to events/tasks.py
"""

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

from .models import Event, EventSyncLog

logger = logging.getLogger(__name__)


@shared_task
def check_completed_calendar_events():
    """
    Find calendar events that have ended and mark corresponding app events as completed.
    
    Called every 15 minutes by Celery Beat.
    Rule: If calendar_end_time is in the past, mark event as completed.
    """
    now = timezone.now()
    
    # Find events that:
    # 1. Are synced from calendar (have calendar_end_time)
    # 2. Are NOT already completed
    # 3. Have calendar_end_time in the past
    candidates = Event.objects.filter(
        calendar_end_time__isnull=False,  # Has calendar sync
        calendar_end_time__lt=now,  # Calendar event has ended
    ).exclude(
        status='completed'  # Not already marked completed
    ).exclude(
        status='cancelled'  # Skip cancelled
    )
    
    completed_count = 0
    error_count = 0
    
    for event in candidates:
        try:
            # Skip if already manually marked completed
            # (in case user beat the task to it)
            if event.status == 'completed':
                continue
            
            # Auto-mark as completed
            old_status = event.status
            event.status = Event.Status.COMPLETED
            event.completed_at = event.calendar_end_time  # Use calendar time as source of truth
            event.save()
            
            # Log the sync action
            EventSyncLog.objects.create(
                event=event,
                sync_direction='pull',  # From calendar perspective
                status='success',
                synced_fields=['status', 'completed_at'],
                changes={
                    'status': {'old': old_status, 'new': 'completed'},
                    'completed_at': str(event.calendar_end_time)
                },
                notes=f"Auto-completed: calendar event ended at {event.calendar_end_time}"
            )
            
            completed_count += 1
            logger.info(f"Auto-completed event {event.id}: {event}")
            
        except Exception as e:
            error_count += 1
            logger.error(f"Error auto-completing event {event.id}: {str(e)}")
            
            # Log the failure
            try:
                EventSyncLog.objects.create(
                    event=event,
                    sync_direction='pull',
                    status='error',
                    error_message=str(e),
                    notes="Failed to auto-complete calendar event"
                )
            except:
                pass
    
    logger.info(
        f"check_completed_calendar_events: {completed_count} completed, "
        f"{error_count} errors, {candidates.count()} total candidates"
    )
    
    return {
        'completed': completed_count,
        'errors': error_count,
        'candidates': candidates.count()
    }


# ============================================================================
# ALTERNATIVE: Manual completion on demand (for admin/UI)
# ============================================================================

def attempt_complete_from_calendar(event):
    """
    Try to complete an event based on its calendar status.
    Called from admin actions or API endpoints.
    
    Returns: (success: bool, message: str, updated: bool)
    """
    
    # Check if calendar event has completed
    if not event.calendar_end_time:
        return False, "No calendar event linked", False
    
    now = timezone.now()
    if now < event.calendar_end_time:
        gap = (event.calendar_end_time - now).total_seconds() / 60  # minutes
        return False, f"Calendar event ends in {gap:.0f} minutes", False
    
    # Calendar has ended, mark as completed
    if event.status == 'completed':
        return True, "Already completed", False
    
    try:
        old_status = event.status
        event.status = Event.Status.COMPLETED
        event.completed_at = event.calendar_end_time
        event.save()
        
        EventSyncLog.objects.create(
            event=event,
            sync_direction='pull',
            status='success',
            synced_fields=['status', 'completed_at'],
            changes={
                'status': {'old': old_status, 'new': 'completed'},
                'completed_at': str(event.calendar_end_time)
            },
            notes="Manually triggered calendar completion"
        )
        
        return True, "Event marked as completed", True
        
    except Exception as e:
        logger.error(f"Error completing event {event.id}: {str(e)}")
        return False, str(e), False


# ============================================================================
# VALIDATION: Check readiness to create timesheet
# ============================================================================

def validate_timesheet_readiness(event):
    """
    Check if an event is ready to have a timesheet entry created.
    
    Returns: (is_ready: bool, reason: str, recommendations: list)
    """
    
    issues = []
    recommendations = []
    
    # 1. Check calendar completion
    if event.calendar_end_time:
        now = timezone.now()
        if now < event.calendar_end_time:
            gap = (event.calendar_end_time - now).total_seconds() / 60  # minutes
            issues.append(f"Calendar event hasn't finished yet ({gap:.0f} min remaining)")
            recommendations.append(f"Wait until {event.calendar_end_time.strftime('%Y-%m-%d %H:%M')}")
    
    # 2. Check app status
    if event.status != 'completed':
        issues.append(f"Event status is '{event.status}', not 'completed'")
        if event.status == 'in_progress':
            recommendations.append("Mark the event as completed")
        else:
            recommendations.append(f"Move event from '{event.status}' to 'completed'")
    
    # 3. Check for invoiced timesheets
    invoiced = event.timesheet_entries.filter(is_billed=True).exists()
    if invoiced:
        issues.append("Event has already been invoiced")
        recommendations.append("Cannot create new timesheet entries for invoiced events")
    
    # Success criteria
    is_ready = len(issues) == 0
    reason = "; ".join(issues) if issues else "Ready to log time"
    
    return is_ready, reason, recommendations


# ============================================================================
# ADMIN ACTION: Trigger completion check for single event
# ============================================================================

def admin_action_check_completion(modeladmin, request, queryset):
    """
    Django admin action: Try to auto-complete selected events based on calendar.
    
    Add to EventAdmin:
        actions = ['action_check_completion']
        
        def action_check_completion(self, request, queryset):
            return admin_action_check_completion(self, request, queryset)
        action_check_completion.short_description = "Check calendar and auto-complete"
    """
    from django.contrib import messages
    
    completed = 0
    already_done = 0
    waiting = 0
    errors = 0
    
    for event in queryset:
        success, msg, updated = attempt_complete_from_calendar(event)
        
        if not success:
            if "ends in" in msg:
                waiting += 1
            else:
                errors += 1
        elif not updated:
            already_done += 1
        else:
            completed += 1
    
    msg = f"✓ Completed: {completed} | Already done: {already_done} | Waiting: {waiting} | Errors: {errors}"
    messages.success(request, msg)
