import json

from django.db import models
from django.utils import timezone

from clients.models import Client
from core.models import TenantModel

# timesheets/models.py
from .managers import TimesheetManager  # Import your new file


# Global default categories editable by staff
class DefaultWorkCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)
    metadata_schema = models.JSONField(default=list, blank=True, help_text="List of extra field names")

    def __str__(self):
        return self.name


def get_unbilled_total(self):
    from timesheets.models import TimesheetEntry

    return (
        TimesheetEntry.objects.filter(client=self, is_billed=False).aggregate(
            total=models.Sum(models.F("hours") * models.F("hourly_rate"))
        )["total"]
        or 0
    )


class WorkCategory(TenantModel):
    user = models.ForeignKey("core.User", on_delete=models.CASCADE)
    name = models.CharField(max_length=50)  # e.g., "Meeting", "Development"

    # Example: ["Attendees", "Location"] or empty [] for simple comments
    metadata_schema = models.JSONField(default=list, blank=True, help_text="List of extra field names")

    def __str__(self):
        return self.name


class TimesheetEntry(TenantModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="timesheets")
    category = models.ForeignKey(WorkCategory, on_delete=models.SET_NULL, null=True, blank=True)
    todo = models.ForeignKey("todos.Todo", on_delete=models.SET_NULL, null=True, blank=True, related_name="timesheet_entries")
    date = models.DateField(default=timezone.now)
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)

    is_billed = models.BooleanField(default=False)
    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="billed_timesheets"
    )

    objects = TimesheetManager()  # Attach it here

    class Meta:
        ordering = ["-date"]

    # Defined only once
    metadata = models.JSONField(default=dict, blank=True)

    @property
    def formatted_metadata(self):
        """
        Returns a string of metadata for the Timesheet Report or Template.
        Accessed as: {{ entry.formatted_metadata }}
        """
        if not self.metadata:
            return ""

        # Create the string
        text = ", ".join([f"{k}: {v}" for k, v in self.metadata.items() if v])

        # Escape characters that break LaTeX if they appear in your metadata
        # Order matters: escape backslash first!
        text = text.replace("\\", r"\textbackslash{}")
        text = text.replace("&", r"\&")
        text = text.replace("%", r"\%")
        text = text.replace("$", r"\$")
        text = text.replace("#", r"\#")
        text = text.replace("_", r"\_")
        text = text.replace("{", r"\{")
        text = text.replace("}", r"\}")
        text = text.replace("~", r"\textasciitilde{}")
        text = text.replace("^", r"\textasciicircum{}")
        
        return text

    @property
    def metadata_json(self):
        """Returns metadata as a safe JSON string for HTML attributes."""
        return json.dumps(self.metadata)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Timesheet Entries"

    def __str__(self):
        return f"{self.date} - {self.client.name} ({self.hours} hrs)"

    @property
    def total_value(self):
        return self.hours * self.hourly_rate
