from django.db import models
from django.utils import timezone
from core.models import TenantModel
from clients.models import Client


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
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
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
        return f"{self.title} ({self.client.name})"
    
    def mark_completed(self):
        """Mark this todo as completed."""
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save()
    
    def mark_cancelled(self):
        """Mark this todo as cancelled."""
        self.status = self.Status.CANCELLED
        self.save()
    
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
