from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from core.models import TenantModel
from clients.models import Client
from .managers import InvoiceManager

class Invoice(TenantModel):
    class TaxMode(models.TextChoices):
        NONE = 'NONE', 'Exempt (No VAT)'
        FULL = 'FULL', 'VAT on Whole Invoice'
        MIXED = 'MIXED', 'Mixed (Item-by-Item)'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING = 'PENDING', 'Pending / Sent'
        PAID = 'PAID', 'Paid'
        OVERDUE = 'OVERDUE', 'Overdue'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class BillingType(models.TextChoices):
        PRODUCT = 'PRODUCT', 'Product-based'
        SERVICE = 'SERVICE', 'Service-based'

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')
    number = models.CharField(max_length=50, blank=True)
    date_issued = models.DateField(default=date.today)
    due_date = models.DateField()
    
    billing_type = models.CharField(max_length=10, choices=BillingType.choices, default=BillingType.SERVICE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    tax_mode = models.CharField(max_length=10, choices=TaxMode.choices, default=TaxMode.NONE)
    
    # Financial Snapshots (Keep these - they are your "Source of Truth")
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Document Storage
    latex_content = models.TextField(blank=True, help_text="The raw LaTeX source used to generate the PDF.")
    last_generated = models.DateTimeField(null=True, blank=True)

    objects = InvoiceManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'number'], name='unique_invoice_per_tenant')
        ]
        ordering = ['-date_issued', '-id']

    def __str__(self):
        return f"{self.number or 'DRAFT'} - {self.client.name}"

class InvoiceItem(models.Model):
    class Preset(models.TextChoices):
        CONSULTING = 'Consulting', 'Professional Consulting'
        DEVELOPMENT = 'Development', 'Software Development'
        DESIGN = 'Design', 'Graphic Design'
        SUPPORT = 'Support', 'Technical Support'
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_taxable = models.BooleanField(default=True)

    @property
    def row_subtotal(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)