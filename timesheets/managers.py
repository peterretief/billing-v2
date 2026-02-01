# timesheets/managers.py
from django.db import models
from django.db.models import F, Sum


class TimesheetManager(models.Manager):
    def unbilled(self, user):
        return self.filter(user=user, is_billed=False)

    def total_unbilled_value(self, user, client=None):
        queryset = self.unbilled(user)
        if client:
            queryset = queryset.filter(client=client)
        
        # Calculation happens at the database level for speed
        result = queryset.aggregate(
            total=Sum(F('hours') * F('hourly_rate'))
        )
        return result['total'] or 0