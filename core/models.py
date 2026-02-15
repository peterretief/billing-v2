from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import TenantManager


class User(AbstractUser):
    """
    Custom User: Email is the primary identity.
    """
    email = models.EmailField(
        unique=True, 
        blank=False, 
        error_messages={'unique': "A user with that email already exists."}
    )
    is_ops = models.BooleanField(default=False)
    added_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='added_users')

    REQUIRED_FIELDS = ['email'] 

    def __str__(self):
        return self.username


class OpsManager(User):
    class Meta:
        proxy = True

    def get_portfolio(self):
        """Returns all profiles assigned to this manager's profile."""
        # We look for UserProfiles where the user was added by THIS manager
        return UserProfile.objects.filter(user__added_by=self)

    def get_portfolio_stats(self):
        from collections import defaultdict
        from decimal import Decimal

        from invoices.models import Invoice

        managed_user_ids = self.added_users.values_list('id', flat=True)
        
        # Eagerly load related data to prevent N+1 query problems in the loop
        portfolio_invoices = Invoice.objects.filter(
            user_id__in=managed_user_ids
        ).select_related('user__profile').prefetch_related('payments')

        stats_by_currency = defaultdict(lambda: {
            'revenue': Decimal('0.00'),
            'outstanding': Decimal('0.00')
        })

        for invoice in portfolio_invoices:
            # Fallback to a default currency if not set on the user's profile
            currency = invoice.user.profile.currency or 'N/A'
            
            # The invoice.total_paid property will use the prefetched payments
            balance_due = invoice.balance_due
            
            stats_by_currency[currency]['revenue'] += invoice.total_amount
            stats_by_currency[currency]['outstanding'] += balance_due
            
        # Return a sorted list of tuples (currency, stats_dict) for predictable order
        return sorted(stats_by_currency.items())    


class TenantModel(models.Model):
    """
    Abstract base class: Every model inheriting from this 
    is automatically isolated by user.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name="%(class)s_related"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        abstract = True

class UserProfile(models.Model):
    """
    Tenant Settings: Tax rates, banking, and branding.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    show_onboarding_tips = models.BooleanField(default=True)
    monthly_target = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=50000.00,
        help_text="Your monthly revenue goal (e.g., 50000)"
    )

    initial_setup_complete = models.BooleanField(default=False)

    # Business Details
    company_name = models.CharField(max_length=255, blank=True)
    business_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    currency = models.CharField(max_length=3, default='R', help_text="e.g. R, $, €")
    invoice_footer = models.TextField(blank=True, 
                                      default="Please use the invoice number as the payment reference.",  # noqa: E501
                                      help_text="Footer notes for invoices.")
    # Tax & Registration
    is_vat_registered = models.BooleanField(default=False)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, 
                                   default=Decimal('15.00'))
    vat_number = models.CharField(max_length=50, blank=True, 
                                  verbose_name="VAT Number")
    tax_number = models.CharField(max_length=50, blank=True, 
                                  verbose_name="Income Tax Number")
    vendor_number = models.CharField(max_length=50, blank=True, 
                                     verbose_name="Vendor Number")

    # Banking
    bank_name = models.CharField(max_length=100, blank=True)
    account_holder = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)
    swift_bic = models.CharField(max_length=20, blank=True, 
                                 verbose_name="SWIFT/BIC Code")

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
    invoice = models.ForeignKey('invoices.Invoice', on_delete=models.SET_NULL,
                                 null=True, related_name='audit_logs')
    action_type = models.CharField(max_length=50, default="AUTO_GENERATE")
    details = models.JSONField() 
    is_anomaly = models.BooleanField(default=False)
    ai_comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action_type} - {self.created_at.date()} - " \
           f"Anomaly: {self.is_anomaly}"