from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone

from clients.models import Client
from core.models import TenantModel

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

    is_template = models.BooleanField(
        default=False, 
        db_index=True,
        help_text="If checked, this invoice will be used " \
        "as a base for recurring monthly billing."
    )

    is_emailed = models.BooleanField(default=False)
    emailed_at = models.DateTimeField(null=True, blank=True)
    last_email_error = models.TextField(null=True, blank=True) # Great for debugging

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')
    number = models.CharField(max_length=50, blank=True)
    date_issued = models.DateField(default=date.today)
    due_date = models.DateField()
    
    billing_type = models.CharField(max_length=10, 
                                    choices=BillingType.choices, 
                                    default=BillingType.SERVICE)
    status = models.CharField(max_length=10, 
                              choices=Status.choices, default=Status.DRAFT)
    tax_mode = models.CharField(max_length=10, 
                                choices=TaxMode.choices, default=TaxMode.NONE)
    
    # Financial Snapshots (Keep these - they are your "Source of Truth")
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Document Storage
    latex_content = models.TextField(blank=True, 
                                     help_text="The raw LaTeX source used to " \
                                     "generate the PDF.")
    last_generated = models.DateTimeField(null=True, blank=True)

    objects = InvoiceManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'number'], 
                                    name='unique_invoice_per_tenant')
        ]
        ordering = ['-date_issued', '-id']

    @property
    def invoice_number(self):
        return self.number

    @invoice_number.setter
    def invoice_number(self, value):
        self.number = value


    @property
    def calculated_subtotal(self):
        from decimal import Decimal
    
        # 1. Check for Billed Items (Direct items or generated from timesheets)
        item_total = sum(
            (item.quantity * item.unit_price for item in self.billed_items.all()), 
            Decimal('0.00')
        )
    
        # 2. If there are items, they are the ONLY source of truth.
        if item_total > 0:
            return item_total
    
        # 3. If NO items exist, fall back to the raw timesheet hours
        timesheet_total = sum(
            (ts.hours * ts.hourly_rate for ts in self.billed_timesheets.all()), 
            Decimal('0.00')
        )
    
        return timesheet_total


    @property
    def calculated_vat(self):
        from decimal import Decimal

        if self.tax_mode == self.TaxMode.NONE:
            return Decimal('0.00')

        # Ensure user profile and vat_rate exist, with a fallback.
        try:
            rate = self.user.profile.vat_rate / Decimal(100)
        except (AttributeError, TypeError):
            rate = Decimal('0.00') # Fallback if profile or vat_rate is not set

        taxable_subtotal = Decimal('0.00')

        if self.tax_mode == self.TaxMode.FULL:
            # VAT on the whole invoice subtotal
            taxable_subtotal = self.calculated_subtotal
        
        elif self.tax_mode == self.TaxMode.MIXED:
            # VAT only on taxable items
            item_total = sum(
                item.total for item in self.billed_items.filter(is_taxable=True)
            )
            # You might want to decide if timesheets can be taxable in mixed mode.
            # For now, we'll assume they are not individually taxable.
            taxable_subtotal = item_total

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
        # Ensure both values are Decimal for proper arithmetic
        total = Decimal(str(self.total_amount)) if self.total_amount else Decimal('0.00')
        return total - self.total_paid
    # --- Sync Snapshot Fields ---

    @property
    def is_locked(self):
        """
        Invoice is immutable if it has been sent to the client (PENDING) 
        or processed further (PAID, OVERDUE, CANCELLED).
        """
        return self.status != self.Status.DRAFT

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
    

class Payment(TenantModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date_paid = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True, null=True) # Ensure blank=True is here

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.amount > self.invoice.balance_due:
            currency = self.user.profile.currency
            raise ValidationError(
                f"Payment amount ({currency} {self.amount}) cannot exceed the balance due ({currency} {self.invoice.balance_due})"
            )
        if self.amount <= 0:
            raise ValidationError("Payment amount must be greater than zero")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        # Auto-update invoice status if balance is now zero
        inv = self.invoice
        if inv.balance_due <= 0:
            inv.status = 'PAID'
            inv.save()

    def __str__(self):
        return f"{self.user.profile.currency} {self.amount} for {self.invoice.number}"  
    

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
        return f"{self.tax_type} Payment - {self.user.profile.currency} {self.amount} ({self.payment_date})"
    
