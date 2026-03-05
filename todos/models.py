from django.db import models
from django.utils import timezone
from core.models import TenantModel
from clients.models import Client


class TodoManager(models.Manager):
    """Custom manager for Todo with data validation and checking methods."""
    
    def check_missing_category(self):
        """Get todos without a category assigned."""
        return self.filter(category__isnull=True)
    
    def check_missing_description(self):
        """Get todos without a description."""
        return self.filter(description__exact="")
    
    def check_missing_estimated_hours(self):
        """Get todos without estimated hours set."""
        return self.filter(estimated_hours__isnull=True)
    
    def check_overdue(self):
        """Get todos that are overdue (due_date in past, not completed/cancelled)."""
        today = timezone.now().date()
        return self.filter(
            due_date__lt=today
        ).exclude(
            status__in=["completed", "cancelled"]
        )
    
    def check_due_soon(self, days=7):
        """Get todos due within X days."""
        today = timezone.now().date()
        future_date = today + timezone.timedelta(days=days)
        return self.filter(
            due_date__range=[today, future_date]
        ).exclude(
            status__in=["completed", "cancelled"]
        )
    
    def check_linked_timesheets(self):
        """Get todos that have linked timesheet entries."""
        return self.filter(timesheet_entries__isnull=False).distinct()
    
    def check_unlinked_timesheets(self):
        """Get todos without any linked timesheet entries."""
        return self.filter(timesheet_entries__isnull=True)
    
    def check_incomplete_logging(self):
        """Get todos where logged hours don't match estimated hours."""
        todos = []
        
        for todo in self.filter(estimated_hours__isnull=False):
            linked_hours = sum(entry.hours for entry in todo.timesheet_entries.all())
            if linked_hours < todo.estimated_hours:
                todos.append(todo)
        
        return todos
    
    def check_no_activity(self, days=30):
        """Get todos not updated in the last X days."""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(updated_at__lt=cutoff_date).exclude(
            status__in=["completed", "cancelled"]
        )
    
    def check_data_quality_report(self, user=None):
        """Get a comprehensive data quality report."""
        base_qs = self.filter(user=user) if user else self.all()
        
        report = {
            'total_todos': base_qs.count(),
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


class Todo(TenantModel):
    """
    Task/Todo linked to a client. Users can track todos and create timesheets from them.
    """
    
    class Status(models.TextChoices):
        BACKLOG = "backlog", "Backlog"
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
    
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"
    
    # Custom manager for data validation and checking
    objects = TodoManager()
    
    category = models.ForeignKey(
        'timesheets.WorkCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="todos",
        help_text="Work category for this task"
    )
    description = models.TextField(blank=True, default="", help_text="Description (saved to category)")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="todos")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated hours to complete this task"
    )
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Todo"
        verbose_name_plural = "Todos"
    
    def __str__(self):
        cat_name = self.category.name if self.category else "Uncategorized"
        return f"{cat_name} ({self.client.name})"
    
    def mark_completed(self):
        """Mark this todo as completed."""
        # Check if completion is allowed
        linked_timesheet = self.timesheet_entries.first()
        if linked_timesheet and linked_timesheet.is_billed:
            raise ValueError("Cannot complete a todo with an invoiced timesheet.")
        
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save()
    
    def mark_cancelled(self):
        """Mark this todo as cancelled."""
        # Check for linked timesheets
        linked_timesheet = self.timesheet_entries.first()
        
        if linked_timesheet:
            if linked_timesheet.is_billed:
                raise ValueError("Cannot cancel a todo with an invoiced timesheet.")
            else:
                # Delete non-invoiced timesheet when cancelling (maintain integrity)
                linked_timesheet.delete()
        
        self.status = self.Status.CANCELLED
        self.save()
    
    def can_be_modified(self):
        """Check if todo can be edited (no linked invoiced timesheet)."""
        linked_timesheet = self.timesheet_entries.first()
        if linked_timesheet and linked_timesheet.is_billed:
            return False
        return True
    
    def get_linked_timesheet_status(self):
        """Get status of linked timesheet if any."""
        linked_timesheet = self.timesheet_entries.first()
        if not linked_timesheet:
            return None
        
        return {
            'exists': True,
            'is_billed': linked_timesheet.is_billed,
            'date': linked_timesheet.date,
            'hours': linked_timesheet.hours,
        }
    
    @property
    def is_overdue(self):
        """Check if todo is overdue."""
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
        """Get list of data quality issues for this todo."""
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
        """Check if todo passes all data quality checks."""
        return len(self.get_data_quality_issues()) == 0


class GoogleCalendarCredential(TenantModel):
    """Store Google Calendar OAuth credentials for users."""
    
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    sync_enabled = models.BooleanField(default=True)
    calendar_id = models.CharField(max_length=255, blank=True, null=True)
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