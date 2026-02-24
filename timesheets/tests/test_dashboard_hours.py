from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from core.tests import BaseBillingTest
from timesheets.models import TimesheetEntry


class TimesheetDashboardHoursTest(BaseBillingTest):
    def test_monthly_hours_sum_on_dashboard(self):
        today = timezone.now().date()
        # Create timesheet entries for this month
        TimesheetEntry.objects.create(
            user=self.user, client=self.client_obj, date=today, hours=Decimal("2.5"), hourly_rate=Decimal("100.00")
        )
        TimesheetEntry.objects.create(
            user=self.user, client=self.client_obj, date=today, hours=Decimal("3.0"), hourly_rate=Decimal("120.00")
        )
        # Create an entry for last month (should not be counted)
        last_month = today.replace(day=1) - timezone.timedelta(days=1)
        TimesheetEntry.objects.create(
            user=self.user, client=self.client_obj, date=last_month, hours=Decimal("5.0"), hourly_rate=Decimal("90.00")
        )
        self.test_client.login(username=self.user.username, password=self.password)
        url = reverse("timesheets:timesheet_list")
        response = self.test_client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check that the sum of this month's hours appears in the response
        self.assertContains(response, "5.5")
