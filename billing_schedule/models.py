from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TenantModel


class BillingPolicyQuerySet(models.QuerySet):
    def due_today(self):
        """
        The Brain: Determines which policies should fire today based on
        the calendar date and special rules.
        """
        today = timezone.now().date()

        # --- Logic for First Working Day ---
        # A day is the 'First Working Day' if:
        # 1. It is a weekday (Mon-Fri)
        # 2. No previous weekdays existed in this month yet.
        is_first_work_day = False
        if today.weekday() < 5:  # It's currently a weekday
            if today.day == 1:
                is_first_work_day = True
            elif today.day == 2 and today.weekday() == 0:  # Mon the 2nd (Sat was 1st)
                is_first_work_day = True
            elif today.day == 3 and today.weekday() == 0:  # Mon the 3rd (Sat/Sun were 1st/2nd)
                is_first_work_day = True

        # --- Filter Logic ---
        # We want policies where:
        # (The run_day matches today) OR (The rule is WORK and today is the first work day)
        query = Q(run_day=today.day)
        if is_first_work_day:
            query |= Q(special_rule="WORK")

        return self.filter(query, is_active=True)


class BillingPolicy(TenantModel):
    name = models.CharField(max_length=100)

    # run_day is optional because 'First Working Day' doesn't need a fixed date
    run_day = models.PositiveSmallIntegerField(null=True, blank=True)

    SPECIAL_RULES = [
        ("NONE", "Exact Date Only"),
        ("WORK", "First Working Day"),
    ]
    special_rule = models.CharField(max_length=10, choices=SPECIAL_RULES, default="NONE")

    is_active = models.BooleanField(default=True)

    objects = BillingPolicyQuerySet.as_manager()

    class Meta:
        verbose_name = "Billing Policy"
        verbose_name_plural = "Billing Policies"
        # Adjusted constraint: Allow a user to have an 'Exact Date' policy
        # and a 'Special Rule' policy without clashing.
        unique_together = ("user", "run_day", "special_rule")

    def __str__(self):
        if self.special_rule == "WORK":
            return f"{self.name} (1st Working Day)"
        return f"{self.name} (Day {self.run_day})"
