from datetime import datetime
from django.db import models
from django.core.validators import MinValueValidator
from core.models import TenantModel
from clients.models import Client
from decimal import Decimal

from .managers import InvoiceManager  # Import it here
from decimal import Decimal, ROUND_HALF_UP


class Invoice(TenantModel):
    class Status(models.TextChoices):
        DRAFT = 'DF', 'Draft'
        SENT = 'ST', 'Sent'
        PAID = 'PD', 'Paid'
        CANCELLED = 'CL', 'Cancelled'

    BILLING_CHOICES = [
        ('product', 'Product-based (Qty/Price)'),
        ('service', 'Service-based (Hours/Rate)'),
    ]
    billing_type = models.CharField(max_length=10, choices=BILLING_CHOICES, default='service')

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')
    number = models.CharField(max_length=50)
    date_issued = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=2, choices=Status.choices, default=Status.DRAFT)
    
    # Store the generated LaTeX here to avoid the "ghosting" issues of the old project
    latex_content = models.TextField(blank=True, help_text="The generated LaTeX source for this invoice")
    
    # Optional: Track if the PDF has been generated
    last_generated = models.DateTimeField(null=True, blank=True)


    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending / Sent'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('VOID', 'Void / Cancelled'),
    ]
    
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='DRAFT'
    )

    tax_exempt = models.BooleanField(default=False, help_text="Check if this invoice should not include VAT")

    objects = InvoiceManager()  # Assign the custom manager

    @property
    def subtotal(self):
        # We sum up the 'total' property of all linked items
        total = sum((item.quantity * item.unit_price for item in self.items.all()), 0)
        return total

    @property
    def total_amount(self):
        if self.tax_exempt:
            amount = Decimal(self.subtotal)
        else:
            tax_rate = getattr(self.user.profile, 'tax_rate', 15)
            amount = Decimal(self.subtotal) * (1 + (Decimal(tax_rate) / 100))
    
        # This rounds to exactly 2 decimal places (0.01)
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def total_amount(self):
        # Defaulting to 15% VAT for South Africa
        tax_rate = getattr(self.user.profile, 'tax_rate', 15)
        return Decimal(self.subtotal) * (1 + (tax_rate / 100))

    @property
    def taxable_subtotal(self):
        """Sums up only items where is_taxable=True"""
        # We use .all() and filter in Python to avoid extra database hits
        return sum((item.row_subtotal for item in self.items.all() if item.is_taxable), Decimal('0.00'))

    @property
    def non_taxable_subtotal(self):
        """Sums up items where is_taxable=False"""
        return sum((item.row_subtotal for item in self.items.all() if not item.is_taxable), Decimal('0.00'))

    @property
    def vat_amount(self):
        """Calculates VAT only on the taxable portion"""
        if self.tax_exempt:
            return Decimal('0.00')
        
        # Pulls tax rate from UserProfile (default to 0 if not set)
        tax_rate = getattr(self.user.profile, 'tax_rate', Decimal('0.00'))
        return (self.taxable_subtotal * (tax_rate / 100)).quantize(Decimal('0.01'))

    @property
    def total_amount(self):
        """The final Grand Total"""
        return (self.taxable_subtotal + self.vat_amount + self.non_taxable_subtotal).quantize(Decimal('0.01'))

    class Meta:
        unique_together = ('user', 'number') # Prevents a user from reusing invoice numbers
        ordering = ['-date_issued', '-number']

    def __str__(self):
        return f"{self.number} - {self.client.name}"

class InvoiceItem(models.Model):
    """
    Line items for the invoice. 
    Note: It doesn't need to inherit from TenantModel because it is 
    linked to an Invoice which is already tenant-aware.
    """
    PRESET_DESCRIPTIONS = [
        ('Consulting', 'Professional Consulting'),
        ('Development', 'Software Development'),
        ('Design', 'Graphic Design'),
        ('Support', 'Technical Support'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    is_taxable = models.BooleanField(default=True)

    @property
    def row_subtotal(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    @property
    def total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.description} ({self.invoice.number})"
    

