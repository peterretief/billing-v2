
# Create your models here.
from django.conf import settings
from django.db import models
from django.utils import timezone


class BillingBatch(models.Model):
    """Tracks the billing progress for a specific user on a specific date."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='billing_batches'
    )
    scheduled_date = models.DateField(default=timezone.now)
    is_processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata for the Manager's report
    invoice_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        # Prevents billing the same person twice on the same day
        unique_together = ('user', 'scheduled_date')
        verbose_name_plural = "Billing Batches"

    def __str__(self):
        status = "✅ Done" if self.is_processed else "⏳ Pending"
        return f"{self.user.username} - {self.scheduled_date} ({status})"