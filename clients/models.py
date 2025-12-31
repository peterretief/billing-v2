from django.db import models
from core.models import TenantModel
import re


class Client(TenantModel):
    """
    Client model inheriting from TenantModel. 
    Automatically includes user, created_at, and updated_at.
    """
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    vat_number = models.CharField(max_length=50, blank=True, verbose_name="VAT Number")
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="TAX Number")
    vendor_number = models.CharField(max_length=50, blank=True, verbose_name="Vendor Number")

    client_code = models.CharField(max_length=10, blank=True) 

    def save(self, *args, **kwargs):
        if not self.client_code:
            # 1. Strip non-alphanumeric characters (e.g., "A&B Corp" -> "ABC")
            clean_name = re.sub(r'\W+', '', self.name).upper()
            # 2. Take the first 4 characters
            base_code = clean_name[:4]
            # 3. If the name is very short, pad it
            self.client_code = base_code.ljust(3, 'X')
            
        super().save(*args, **kwargs) 


    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


