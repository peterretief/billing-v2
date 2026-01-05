from django.db import models
from django.utils import timezone
from core.models import TenantModel
from clients.models import Client
from invoices.models import Invoice

def get_unbilled_total(self):
    from timesheets.models import TimesheetEntry
    return TimesheetEntry.objects.filter(
        client=self, 
        is_billed=False
    ).aggregate(total=models.Sum(models.F('hours') * models.F('hourly_rate')))['total'] or 0



class WorkCategory(models.Model):
    user = models.ForeignKey('core.User', on_delete=models.CASCADE)
    name = models.CharField(max_length=50) # e.g., "Meeting", "Development"
    
    # Example: ["Attendees", "Location"] or empty [] for simple comments
    metadata_schema = models.JSONField(default=list, blank=True, help_text="List of extra field names")

    def __str__(self):
        return self.name

class TimesheetEntry(TenantModel):
    category = models.ForeignKey(WorkCategory, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField() # This is your standard comment
    metadata = models.JSONField(default=dict, blank=True) # Stores the actual answers

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='timesheets')
    date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=255)
    
    # Using Decimal for precision in hours and rates
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Automation tracking
    is_billed = models.BooleanField(default=False)
    # Link to the invoice once it's generated
    invoice = models.ForeignKey(
        Invoice, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='billed_timesheets'
    )

    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Timesheet Entries"

    def __str__(self):
        return f"{self.date} - {self.client.name} ({self.hours} hrs)"

    @property
    def total_value(self):
        return self.hours * self.hourly_rate
    

