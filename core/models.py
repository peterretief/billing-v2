from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
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

    REQUIRED_FIELDS = ['email'] 

    def __str__(self):
        return self.username

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
    
    monthly_target = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=50000.00,
        help_text="Your monthly revenue goal (e.g., 50000)"
    )

    # Business Details
    company_name = models.CharField(max_length=255, blank=True)
    business_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)

    # Tax & Registration
    is_vat_registered = models.BooleanField(default=False)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('15.00'))
    vat_number = models.CharField(max_length=50, blank=True, verbose_name="VAT Number")
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="Income Tax Number")
    vendor_number = models.CharField(max_length=50, blank=True, verbose_name="Vendor Number")

    # Banking
    bank_name = models.CharField(max_length=100, blank=True)
    account_holder = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)
    swift_bic = models.CharField(max_length=20, blank=True, verbose_name="SWIFT/BIC Code")

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