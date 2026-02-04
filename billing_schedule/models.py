# billing_scheduler/models.py
from django.db import models

# billing_schedule/models.py
from core.models import TenantModel


class BillingPolicy(TenantModel):
    name = models.CharField(max_length=100)
    
    # Optional: If special_rule is set, this can be blank
    run_day = models.PositiveSmallIntegerField(null=True, blank=True)
    
    SPECIAL_RULES = [
        ('NONE', 'Exact Date Only'),
        ('WORK', 'First Working Day'),
    ]
    special_rule = models.CharField(
        max_length=10, 
        choices=SPECIAL_RULES, 
        default='NONE'
    )
   
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Billing Policy"
        # Prevents a user from accidentally creating the same schedule twice
        # Link 'user' (from userModel) and 'run_day'
        unique_together = ('user', 'run_day') 
        verbose_name = "Billing Policy"

    def __str__(self):
        if self.special_rule == 'WORK':
            return f"{self.name} (1st Working Day)"
        return f"{self.name} (Day {self.run_day})"