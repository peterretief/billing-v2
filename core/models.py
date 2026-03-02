from decimal import Decimal

import pytz
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import TenantManager


class User(AbstractUser):
    """
    Custom User: Email is the primary identity.
    """

    email = models.EmailField(
        unique=True, blank=False, error_messages={"unique": "A user with that email already exists."}
    )
    added_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="added_users")

    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class TenantModel(models.Model):
    """
    Abstract base class: Every model inheriting from this
    is automatically isolated by user.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="%(class)s_related")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        abstract = True


class UserProfile(models.Model):
    """
    Tenant Settings: Tax rates, banking, and branding.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    timezone = models.CharField(
        max_length=32, default="Africa/Johannesburg", choices=[(tz, tz) for tz in pytz.common_timezones]
    )

    show_onboarding_tips = models.BooleanField(default=True)
    monthly_target = models.DecimalField(
        max_digits=10, decimal_places=2, default=50000.00, help_text="Your monthly revenue goal (e.g., 50000)"
    )

    initial_setup_complete = models.BooleanField(default=False)

    # Business Details
    company_name = models.CharField(max_length=255, blank=True)
    contact_name = models.CharField(max_length=255, blank=True, help_text="Contact person for email preferences.")
    business_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    currency = models.CharField(max_length=3, default="R", help_text="e.g. R, $, €")
    invoice_footer = models.TextField(
        blank=True,
        default="Please use the invoice number as the payment reference.",  # noqa: E501
        help_text="Footer notes for invoices.",
    )
    # Tax & Registration
    is_vat_registered = models.BooleanField(default=False)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("15.00"))
    vat_number = models.CharField(max_length=50, blank=True, verbose_name="VAT Number")
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="Income Tax Number")
    vendor_number = models.CharField(max_length=50, blank=True, verbose_name="Vendor Number")
    tax_year_type = models.CharField(
        max_length=2,
        choices=[
            ("ZA", "South Africa (Mar 1 - Feb 28)"),
            ("US", "United States (Jan 1 - Dec 31)"),
            ("UK", "United Kingdom (Apr 1 - Mar 31)"),
            ("AU", "Australia (Jul 1 - Jun 30)"),
            ("CA", "Canada (Jan 1 - Dec 31)"),
            ("NZ", "New Zealand (Apr 1 - Mar 31)"),
        ],
        default="ZA",
        help_text="Your financial/tax year start date",
    )

    # Banking
    bank_name = models.CharField(max_length=100, blank=True)
    account_holder = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)
    swift_bic = models.CharField(max_length=20, blank=True, verbose_name="SWIFT/BIC Code")

    # Audit & Compliance Settings
    audit_enabled = models.BooleanField(default=False, help_text="Enable anomaly detection for invoices")
    audit_sensitivity = models.CharField(
        max_length=20,
        choices=[
            ("STRICT", "Strict (1.5σ) - Catches ~6.7% outliers"),
            ("MEDIUM", "Medium (2σ) - Catches ~2.3% outliers"),
            ("LENIENT", "Lenient (2.5σ) - Catches ~1.2% outliers"),
        ],
        default="MEDIUM",
        help_text="How aggressive should anomaly detection be?",
    )
    audit_triggers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Which audit checks are enabled",
    )

    def get_audit_triggers(self):
        """Returns audit trigger configuration with sensible defaults."""
        defaults = {
            "detect_zero_total": True,
            "detect_no_items": True,
            "detect_statistical_outliers": True,
            "detect_missing_email": True,
            "detect_vat_mismatch": True,
            "detect_duplicate_items": True,
        }
        if not self.audit_triggers:
            return defaults
        return {**defaults, **self.audit_triggers}

    @property
    def annual_revenue_forecast(self):
        """Calculates the 12-month forecast based on the current target."""
        return self.monthly_target * 12

    @property
    def quarterly_revenue_forecast(self):
        """Calculates the 3-month forecast."""
        return self.monthly_target * 3

    def __str__(self):
        return f"Profile: {self.user.username}"


class BillingAuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.SET_NULL, null=True, related_name="audit_logs")
    action_type = models.CharField(max_length=50, default="AUTO_GENERATE")
    details = models.JSONField()
    is_anomaly = models.BooleanField(default=False)
    ai_comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action_type} - {self.created_at.date()} - Anomaly: {self.is_anomaly}"


class AuditHistory(models.Model):
    """
    Tracks audit decisions and comparisons used for trained anomaly detection.
    Helps build a learning model of what's "normal" for each user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="audit_history")
    invoice = models.OneToOneField("invoices.Invoice", on_delete=models.CASCADE, related_name="audit_decision")
    
    # What triggered the audit
    checks_run = models.JSONField(help_text="Which audit checks were executed")
    flags_raised = models.JSONField(default=list, help_text="List of issues detected")
    comparison_invoices_count = models.IntegerField(default=0, help_text="How many historical invoices were compared")
    
    # Results
    is_flagged = models.BooleanField(default=False)
    was_approved = models.BooleanField(default=False, help_text="User approved despite flag (for learning)")
    approval_reason = models.TextField(blank=True, help_text="Why user approved a flagged invoice")
    
    # Stats from comparison set
    comparison_mean = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True)
    comparison_stddev = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True)
    comparison_cv = models.DecimalField(max_digits=5, decimal_places=3, default=0, null=True, blank=True, help_text="Coefficient of Variation")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Audit History"
        verbose_name_plural = "Audit Histories"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"Audit #{self.id} - Invoice {self.invoice.number} - {'Flagged' if self.is_flagged else 'OK'}"
    
    @property
    def has_sufficient_history(self):
        """Check if comparison set has enough invoices."""
        return self.comparison_invoices_count >= 5


class UserGroup(models.Model):
    """
    Represents a group of users managed by an ops manager or superuser.
    Allows for hierarchical organization of tenant users.
    """

    name = models.CharField(max_length=255)
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_groups",
        help_text="The manager who owns this group. Leave blank for superuser-only groups.",
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("name", "manager")
        verbose_name = "User Group"
        verbose_name_plural = "User Groups"

    def __str__(self):
        if self.manager:
            return f"{self.name} (Manager: {self.manager.username})"
        return f"{self.name} (Global)"

    def can_add_member(self, user):
        """Check if a user can add members to this group."""
        if user.is_superuser:
            return True
        if self.manager and self.manager.id == user.id:
            return True
        return False


class GroupMember(models.Model):
    """
    Represents membership of a user in a group.
    Bound tenant users belong to specific groups managed by ops managers.
    """

    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_memberships")
    role = models.CharField(
        max_length=20,
        choices=[
            ("TENANT", "Tenant"),
            ("MANAGER", "Manager"),
            ("ADMIN", "Admin"),
        ],
        default="TENANT",
        help_text="Role of this user within the group",
    )
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="added_group_members")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "user")
        verbose_name = "Group Member"
        verbose_name_plural = "Group Members"

    def __str__(self):
        return f"{self.user.username} in {self.group.name} ({self.role})"
