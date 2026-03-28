import uuid

from django.db import models
from django.utils import timezone

from clients.models import Client
from core.models import TenantModel


class EventManager(models.Manager):
    """Custom manager for Event with data validation and checking methods."""
    
    def check_missing_category(self):
        """Get events without a category assigned."""
        return self.filter(category__isnull=True)
    
    def check_missing_description(self):
        """Get events without a description."""
        return self.filter(description__exact="")
    
    def check_missing_estimated_hours(self):
        """Get events without estimated hours set."""
        return self.filter(estimated_hours__isnull=True)
    
    def check_overdue(self):
        """Get events that are overdue (due_date in past, not completed/cancelled)."""
        today = timezone.now().date()
        return self.filter(
            due_date__lt=today
        ).exclude(
            status__in=["completed", "cancelled"]
        )
    
    def check_due_soon(self, days=7):
        """Get events due within X days."""
        today = timezone.now().date()
        future_date = today + timezone.timedelta(days=days)
        return self.filter(
            due_date__range=[today, future_date]
        ).exclude(
            status__in=["completed", "cancelled"]
        )
    
    def check_linked_timesheets(self):
        """Get events that have linked timesheet entries."""
        return self.filter(timesheet_entries__isnull=False).distinct()
    
    def check_unlinked_timesheets(self):
        """Get events without any linked timesheet entries."""
        return self.filter(timesheet_entries__isnull=True)
    
    def check_incomplete_logging(self):
        """Get events where logged hours don't match estimated hours."""
        events = []
        
        for event in self.filter(estimated_hours__isnull=False):
            linked_hours = sum(entry.hours for entry in event.timesheet_entries.all())
            if linked_hours < event.estimated_hours:
                events.append(event)
        
        return events
    
    def check_no_activity(self, days=30):
        """Get events not updated in the last X days."""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(updated_at__lt=cutoff_date).exclude(
            status__in=["completed", "cancelled"]
        )
    
    def check_data_quality_report(self, user=None):
        """Get a comprehensive data quality report."""
        base_qs = self.filter(user=user) if user else self.all()
        
        report = {
            'total_events': base_qs.count(),
            'missing_category': base_qs.filter(category__isnull=True).count(),
            'missing_description': base_qs.filter(description__exact="").count(),
            'missing_estimated_hours': base_qs.filter(estimated_hours__isnull=True).count(),
            'overdue': base_qs.filter(due_date__lt=timezone.now().date()).exclude(status__in=["completed", "cancelled"]).count(),
            'due_soon': base_qs.filter(due_date__range=[timezone.now().date(), timezone.now().date() + timezone.timedelta(days=7)]).exclude(status__in=["completed", "cancelled"]).count(),
            'with_timesheet': base_qs.filter(timesheet_entries__isnull=False).distinct().count(),
            'without_timesheet': base_qs.filter(timesheet_entries__isnull=True).count(),
            'incomplete_logging': len([t for t in base_qs.filter(estimated_hours__isnull=False) if sum(e.hours for e in t.timesheet_entries.all()) < t.estimated_hours]),
            'no_activity_30days': base_qs.filter(updated_at__lt=timezone.now() - timezone.timedelta(days=30)).exclude(status__in=["completed", "cancelled"]).count(),
        }
        
        return report


class Event(TenantModel):
    """
    Event/Task linked to a client. Users can track events and create timesheets from them.
    """
    
    class Status(models.TextChoices):
        BACKLOG = "backlog", "Backlog"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
    
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"
    
    # Custom manager for data validation and checking
    objects = EventManager()
    
    category = models.ForeignKey(
        'timesheets.WorkCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        help_text="Work category for this task"
    )
    description = models.TextField(blank=True, default="", help_text="Description (saved to category)")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BACKLOG)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    
    due_date = models.DateField(null=True, blank=True)
    suggested_start_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Suggested start time from slot finder (used for calendar sync)"
    )
    calendar_start_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Event start time from Google Calendar (read-only, synced from calendar)"
    )
    calendar_end_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Event end time from Google Calendar (read-only, synced from calendar)"
    )
    google_calendar_event_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Google Calendar event ID (to prevent duplicates)"
    )
    calendar_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=False,
        null=True,
        blank=True,
        help_text="Unique identifier synced to Google Calendar for robust tracking"
    )
    synced_to_calendar = models.BooleanField(
        default=False,
        help_text="Marked as synced to Google Calendar"
    )
    estimated_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated hours to complete this task"
    )
    
    # Bidirectional sync tracking
    google_calendar_etag = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="eTag for conflict detection with Google Calendar"
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this event was synced with Google Calendar"
    )
    last_synced_from = models.CharField(
        max_length=10,
        choices=[('app', 'App'), ('calendar', 'Calendar')],
        blank=True,
        help_text="Which system was the last source of truth"
    )
    sync_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Sync'),
            ('synced', 'Synced'),
            ('failed', 'Sync Failed'),
        ],
        default='pending',
        help_text="Current sync status with Google Calendar"
    )
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Event"
        verbose_name_plural = "Events"
        indexes = [
            models.Index(fields=['user', 'google_calendar_event_id']),
            models.Index(fields=['user', 'sync_status']),
            models.Index(fields=['last_synced_at']),
        ]
    
    def __str__(self):
        cat_name = self.category.name if self.category else "Uncategorized"
        return f"{cat_name} ({self.client.name})"
    
    def mark_completed(self):
        """Mark this event as completed."""
        # Check calendar completion gate - event must have finished on calendar
        if self.calendar_end_time:
            if timezone.now() < self.calendar_end_time:
                gap_seconds = (self.calendar_end_time - timezone.now()).total_seconds()
                gap_hours = gap_seconds / 3600
                raise ValueError(
                    f"Cannot complete this event yet. "
                    f"The calendar event is still running ({gap_hours:.1f} hours remaining). "
                    f"It ends on {self.calendar_end_time.strftime('%Y-%m-%d %H:%M')}."
                )
        
        # Check if completion is allowed
        linked_timesheet = self.timesheet_entries.first()
        if linked_timesheet and linked_timesheet.is_billed:
            raise ValueError("Cannot complete an event with an invoiced timesheet.")
        
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save()
    
    def mark_cancelled(self):
        """Mark this event as cancelled."""
        # Check for linked timesheets
        linked_timesheet = self.timesheet_entries.first()
        
        if linked_timesheet:
            if linked_timesheet.is_billed:
                raise ValueError("Cannot cancel an event with an invoiced timesheet.")
            else:
                # Delete non-invoiced timesheet when cancelling (maintain integrity)
                linked_timesheet.delete()
        
        self.status = self.Status.CANCELLED
        self.save()
    
    def can_be_modified(self):
        """Check if event can be edited (no linked invoiced timesheet)."""
        linked_timesheet = self.timesheet_entries.first()
        if linked_timesheet and linked_timesheet.is_billed:
            return False
        return True
    
    def get_linked_timesheet_status(self):
        """Get status of linked timesheet if any for this event."""
        linked_timesheet = self.timesheet_entries.first()
        if not linked_timesheet:
            return None
        
        return {
            'exists': True,
            'is_billed': linked_timesheet.is_billed,
            'date': linked_timesheet.date,
            'hours': linked_timesheet.hours,
        }
    
    def can_create_timesheet_entry(self):
        """
        Check if a timesheet entry can be created for this event.
        
        Rule: Event can only be linked to timesheet if it has completed on the calendar.
        See: docs/CALENDAR_INTEGRATION_RULES.md - Rule 1
        
        Returns: (is_allowed: bool, reason: str)
        """
        # 1. Calendar completion check
        if self.calendar_end_time:
            if timezone.now() < self.calendar_end_time:
                remaining = (self.calendar_end_time - timezone.now()).total_seconds() / 60  # minutes
                return False, f"Calendar event hasn't finished yet ({remaining:.0f} min remaining)"
        
        # 2. Status check
        if self.status != self.Status.COMPLETED:
            return False, f"Event status is '{self.status}', must be 'completed'"
        
        # 3. Invoice check
        if self.timesheet_entries.filter(is_billed=True).exists():
            return False, "Event already has invoiced timesheet entries"
        
        return True, "Ready to create timesheet entry"
    
    def validate_timesheet_readiness(self):
        """
        Get comprehensive validation report for timesheet creation.
        
        Returns: {
            'is_ready': bool,
            'issues': [list of issues],
            'recommendations': [list of fixes]
        }
        """
        issues = []
        recommendations = []
        
        # Check if event was deleted on calendar
        if self.calendar_end_time is None and self.synced_to_calendar and self.sync_status == 'failed':
            issues.append("This event was deleted on Google Calendar")
            recommendations.append("This event can no longer be linked to timesheets as it was removed from your calendar")
        
        # Calendar completion
        if self.calendar_end_time:
            if timezone.now() < self.calendar_end_time:
                gap = (self.calendar_end_time - timezone.now()).total_seconds() / 60
                issues.append(f"Calendar event hasn't finished yet ({gap:.0f} min remaining)")
                recommendations.append(
                    f"Check in at {self.calendar_end_time.strftime('%Y-%m-%d %H:%M')}"
                )
        
        # Status validation
        if self.status != 'completed':
            issues.append(f"Event status is '{self.status}', not 'completed'")
            if self.status in ['backlog']:
                recommendations.append("Move event to 'In Progress' → 'Completed'")
            elif self.status == 'in_progress':
                recommendations.append("Mark as Completed")
        
        # Invoice check
        if self.timesheet_entries.filter(is_billed=True).exists():
            issues.append("Event has already been invoiced")
            recommendations.append("Cannot create new timesheet entries for invoiced events")
        
        return {
            'is_ready': len(issues) == 0,
            'issues': issues,
            'recommendations': recommendations,
        }
    
    
    @property
    def is_overdue(self):
        """Check if event is overdue."""
        if self.due_date and self.status not in [self.Status.COMPLETED, self.Status.CANCELLED]:
            return self.due_date < timezone.now().date()
        return False
    
    @property
    def get_linked_hours(self):
        """Sum of hours from linked timesheets."""
        return sum(entry.hours for entry in self.timesheet_entries.all())
    
    @property
    def remaining_hours(self):
        """Remaining hours = estimated - linked."""
        if self.estimated_hours:
            return max(self.estimated_hours - self.get_linked_hours, 0)
        return None    
    def get_data_quality_issues(self):
        """Get list of data quality issues for this event."""
        issues = []
        
        if not self.category:
            issues.append("missing_category")
        
        if not self.description:
            issues.append("missing_description")
        
        if not self.estimated_hours:
            issues.append("missing_estimated_hours")
        
        if self.is_overdue:
            issues.append("overdue")
        
        if self.timesheet_entries.count() == 0 and self.status not in ["completed", "cancelled"]:
            issues.append("no_timesheet_linked")
        
        if self.estimated_hours and self.get_linked_hours < self.estimated_hours:
            issues.append("incomplete_logging")
        
        # Check if no activity in 30 days
        cutoff_date = timezone.now() - timezone.timedelta(days=30)
        if self.updated_at < cutoff_date and self.status not in ["completed", "cancelled"]:
            issues.append("no_recent_activity")
        
        return issues
    
    def is_data_quality_ok(self):
        """Check if event passes all data quality checks."""
        return len(self.get_data_quality_issues()) == 0


class GoogleCalendarCredential(TenantModel):
    """Store Google Calendar OAuth credentials for users."""
    
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    sync_enabled = models.BooleanField(default=True)
    calendar_id = models.CharField(max_length=255, blank=True, null=True)
    email_address = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Google Calendar Credential"
        verbose_name_plural = "Google Calendar Credentials"
        unique_together = ('user',)
    
    def __str__(self):
        return f"Google Calendar - {self.user.username}"
    
    def is_token_expired(self):
        """Check if the access token has expired."""
        if self.token_expiry:
            return timezone.now() >= self.token_expiry
        return False


class EventSyncLog(models.Model):
    """Audit trail for all sync operations between app and Google Calendar."""
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='sync_logs')
    sync_direction = models.CharField(
        max_length=20,
        choices=[('push', 'App → Calendar'), ('pull', 'Calendar → App')],
        help_text="Direction of sync"
    )
    status = models.CharField(
        max_length=20,
        choices=[('success', 'Success'), ('error', 'Error')],
        default='success'
    )
    
    # Details about what was synced
    synced_fields = models.JSONField(default=list, help_text="List of fields that were synced")
    changes = models.JSONField(default=dict, help_text="Old and new values for each field")
    
    error_message = models.TextField(blank=True, help_text="Error message if sync failed")
    notes = models.TextField(blank=True, help_text="Additional notes")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Event Sync Log"
        verbose_name_plural = "Event Sync Logs"
        indexes = [
            models.Index(fields=['event', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.event} - {self.sync_direction} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
