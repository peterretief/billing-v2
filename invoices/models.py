from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from core.models import TenantModel
from clients.models import Client
from .managers import InvoiceManager
from django.utils import timezone

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

    @property
    def calculated_subtotal(self):
        return sum(item.row_subtotal for item in self.items.all()) or Decimal('0.00')

    @property
    def calculated_vat(self):
        # Fix: Check tax_mode instead of use_vat
        if self.tax_mode == self.TaxMode.NONE:
            return Decimal('0.00')
        
        taxable_subtotal = sum(
            item.row_subtotal for item in self.items.filter(is_taxable=True)
        ) or Decimal('0.00')
        
        # Pulling the rate from the User's Business Profile
        # Note: Ensure self.user exists (TenantModel usually links to user)
        rate = self.user.profile.vat_rate / 100
        return (taxable_subtotal * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def calculated_total(self):
        return self.calculated_subtotal + self.calculated_vat

    # --- Payment Logic ---

    @property
    def total_paid(self):
        return sum(payment.amount for payment in self.payments.all()) or Decimal('0.00')

    @property
    def balance_due(self):
        # Use the snapshot field or calculated total
        return self.total_amount - self.total_paid

    @property
    def balance_due(self):
        # Use the database field total_amount, not calculated_total
        return self.total_amount - self.total_paid
    # --- Sync Snapshot Fields ---

    def sync_totals(self):
        """Call this before saving to update the snapshot fields."""
        self.subtotal_amount = self.calculated_subtotal
        self.tax_amount = self.calculated_vat
        self.total_amount = self.calculated_total

    def save(self, *args, **kwargs):
        # Automatically update snapshots whenever the invoice is saved
        if self.pk: # Only sync if already created or items exist
            self.sync_totals()
        super().save(*args, **kwargs)

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
    

class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date_paid = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-update invoice status if balance is now zero
        inv = self.invoice
        if inv.balance_due <= 0:
            inv.status = 'PAID'
            inv.save()

    def __str__(self):
        return f"R {self.amount} for {self.invoice.number}"  
    

# invoices/models.py
from core.models import TenantModel  # Import where your TenantModel lives

class VATReport(TenantModel):
    month = models.IntegerField()
    year = models.IntegerField()
    
    # Store the full LaTeX source code
    latex_source = models.TextField()
    
    # Financial snapshots
    net_total = models.DecimalField(max_digits=12, decimal_places=2)
    vat_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        # Since TenantModel provides 'user', we use 'user' here
        unique_together = ('user', 'month', 'year')
        ordering = ['-year', '-month']

    def __str__(self):
        return f"VAT Report {self.year}-{self.month:02d} ({self.user.username})"
    

class TaxPayment(TenantModel):
    payment_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, help_text="e.g., VAT201 Period 2026/01")
    tax_type = models.CharField(max_length=20, default='VAT', choices=[('VAT', 'VAT'), ('INCOME_TAX', 'Income Tax')])

    def __str__(self):
        return f"{self.tax_type} Payment - R {self.amount} ({self.payment_date})"