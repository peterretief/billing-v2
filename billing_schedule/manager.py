# billing_scheduler/managers.py
import calendar
import datetime

from django.db import models


class BillingPolicyQuerySet(models.QuerySet):
    def due_today(self):
        today = datetime.date.today()
        last_day_of_month = calendar.monthrange(today.year, today.month)[1]
        
        # Canonical Logic: 
        # 1. Match the exact day.
        # 2. If it's the last day of the month (e.g., Feb 28), 
        #    catch all policies for days 29, 30, and 31.
        if today.day == last_day_of_month:
            return self.filter(is_active=True, run_day__gte=today.day)
        
        return self.filter(is_active=True, run_day=today.day)