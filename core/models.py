from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom User where email is required and unique.
    """
    # Override the email field to make it unique and required (blank=False)
    email = models.EmailField(
        unique=True, 
        blank=False, 
        error_messages={
            'unique': "A user with that email already exists.",
        }
    )

    # Use the email as the username for login if you prefer, 
    # but for now, we'll keep username + required email.
    REQUIRED_FIELDS = ['email'] 

    def __str__(self):
        return self.username


class TenantModel(models.Model):
    """Inherit from this for every new model you create."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True



class UserProfile(models.Model):
    """The 'Settings' for each tenant."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    company_name = models.CharField(max_length=255, blank=True)

    business_email = models.EmailField(blank=True, help_text="Email that appears on invoices")
    phone = models.CharField(max_length=20, blank=True)
    
    address = models.TextField(blank=True)


    address = models.TextField(blank=True)
    tax_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=15.00, 
        help_text="Set to 0 for No VAT"
    )
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    vat_number = models.CharField(max_length=50, blank=True, verbose_name="VAT Number")
    
    # New Business Fields
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="Income Tax Number")
    vendor_number = models.CharField(max_length=50, blank=True, verbose_name="Vendor Number")

    # Banking Details
    bank_name = models.CharField(max_length=100, blank=True)
    account_holder = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Profile for {self.user.username}"