from decimal import Decimal

from django.utils import timezone

from core.tests import BaseBillingTest
from timesheets.models import TimesheetEntry


class TimesheetLogicTest(BaseBillingTest): # Inherit from our new base
    
    def test_timesheet_calculation(self):
        # self.user and self.client_obj are already waiting for you!
        entry = TimesheetEntry.objects.create(
            user=self.user,
            client=self.client_obj,
            date=timezone.now().date(),
            hours=Decimal('5.00'),
            hourly_rate=Decimal('200.00')
        )
        self.assertEqual(entry.hours * entry.hourly_rate, Decimal('1000.00'))