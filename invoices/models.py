from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.functions import Coalesce
from django.utils import timezone

# from pydantic_core import ValidationError
from clients.models import Client
from core.models import TenantModel

from .managers import InvoiceManager, PaymentManager, CreditNoteManager

# invoices/models.py


class InvoiceEmailStatusLog(TenantModel):
    invoice = models.ForeignKey("Invoice", on_delete=models.CASCADE, related_name="delivery_logs")
    brevo_message_id = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=50)

    # created_at and updated_at are inherited from TenantModel

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice {self.invoice_id} - {self.status} ({self.created_at})"


class Invoice(TenantModel):
    attach_timesheet_to_email = models.BooleanField(
        default=False, help_text="Attach timesheet report PDF to invoice email if created from timesheet."
    )

    def get_latest_delivery_status(self):
        """
        Returns the highest-priority delivery status for this invoice, or None if no logs exist.
        Priority: DELIVERED > SENT > REQUEST > others by created_at.
        """
        priority = {"DELIVERED": 3, "SENT": 2, "REQUEST": 1}
        logs = list(self.delivery_logs.all())
        if not logs:
            return None
        logs.sort(key=lambda l: (priority.get(l.status.upper(), 0), l.created_at), reverse=True)
        return logs[0].status

    def can_record_payment(self):
        """
        Determine if payment can be recorded on this invoice.
        Payment is allowed unless invoice is: PAID, DRAFT, or CANCELLED.
        
        Special case: If invoice has delivery logs showing "delivered" or "sent" 
        but is still in DRAFT status, allow payment (detect orphaned state).
        """
        # Block payment on truly unpayable statuses
        if self.status in [self.Status.PAID, self.Status.CANCELLED]:
            return False
        
        # If DRAFT but has been emailed/sent, allow payment (orphaned state recovery)
        if self.status == self.Status.DRAFT:
            # Check if invoice has delivery logs indicating it was actually sent
            # Note: delivery log status is lowercase (sent, delivered, request)
            if self.delivery_logs.filter(status__in=["sent", "delivered"]).exists():
                return True
            # Otherwise, DRAFT invoices cannot have payments
            return False
        
        # PENDING, OVERDUE, and others can have payments
        return True

    def sync_status_with_delivery(self):
        """
        Detect orphaned invoices (have delivery logs but wrong status) and fix them.
        Returns True if status was corrected.
        """
        # If marked as emailed, status should be at least PENDING
        if self.is_emailed and self.status == self.Status.DRAFT:
            self.status = self.Status.PENDING
            self.save(update_fields=['status'])
            return True
        
        # If has successful delivery logs but still in DRAFT, fix it
        if self.status == self.Status.DRAFT and self.delivery_logs.filter(status__in=["sent", "delivered"]).exists():
            self.status = self.Status.PENDING
            self.is_emailed = True
            if not self.emailed_at:
                from django.utils import timezone
                self.emailed_at = timezone.now()
            self.save(update_fields=['status', 'is_emailed', 'emailed_at'])
            return True
        
        return False


    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending / Sent"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"
        CANCELLED = "CANCELLED", "Cancelled"

    class BillingType(models.TextChoices):
        PRODUCT = "PRODUCT", "Product-based"
        SERVICE = "SERVICE", "Service-based"

    is_template = models.BooleanField(
        default=False,
        db_index=True,
        help_text="If checked, this invoice will be used as a base for recurring monthly billing.",
    )

    is_quote = models.BooleanField(
        default=False,
        db_index=True,
        help_text="If checked, this is a quote. Once accepted, can be converted to an invoice.",
    )

    quote_status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("ACCEPTED", "Accepted"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING",
        null=True,
        blank=True,
        help_text="Tracks quote status: pending, accepted, or rejected.",
    )

    was_originally_quote = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Tracks whether this invoice was originally created as a quote before being converted.",
    )

    is_emailed = models.BooleanField(default=False)
    emailed_at = models.DateTimeField(null=True, blank=True)
    last_email_error = models.TextField(null=True, blank=True)  # Great for debugging

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="invoices")
    number = models.CharField(max_length=50, blank=True)
    date_issued = models.DateField(default=date.today)
    due_date = models.DateField()

    billing_type = models.CharField(max_length=10, choices=BillingType.choices, default=BillingType.SERVICE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    cancellation_reason = models.TextField(blank=True, null=True, help_text="Reason for cancellation")

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
            models.UniqueConstraint(fields=["user", "number"], name="unique_invoice_per_tenant")
        ]
        ordering = ["-date_issued", "-id"]

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
        item_total = sum((item.quantity * item.unit_price for item in self.billed_items.all()), Decimal("0.00"))

        # 2. If there are items, they are the ONLY source of truth.
        if item_total > 0:
            return item_total

        # 3. If NO items exist, fall back to the raw timesheet hours
        timesheet_total = sum((ts.hours * ts.hourly_rate for ts in self.billed_timesheets.all()), Decimal("0.00"))

        return timesheet_total

    @property
    def calculated_vat(self):
        from decimal import Decimal

        # Check if user is VAT registered
        try:
            is_registered = self.user.profile.is_vat_registered
            rate = self.user.profile.vat_rate / Decimal(100)
        except (AttributeError, TypeError):
            is_registered = False
            rate = Decimal("0.00")

        # If not registered, no VAT
        if not is_registered:
            return Decimal("0.00")

        # If registered, apply VAT to all items
        return (self.calculated_subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def calculated_total(self):
        return self.calculated_subtotal + self.calculated_vat

    @property
    def total_paid(self):
        from django.db.models import Sum

        # Sum both cash payments AND applied credits
        result = self.payments.aggregate(
            cash=Coalesce(Sum("amount"), Decimal("0.00")), credits=Coalesce(Sum("credit_applied"), Decimal("0.00"))
        )
        return result["cash"] + result["credits"]


    @property
    def balance_due(self):
        # Ensure both values are Decimal for proper arithmetic
        total = Decimal(str(self.total_amount)) if self.total_amount else Decimal("0.00")
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
        Invoice.objects.update_totals(self)

    def clean(self):
        """
        Business rule: If a PAID invoice is being cancelled, validate it can be cancelled.
        The actual credit note creation happens in save().
        """
        super().clean()
        
        # Check if this invoice exists (has a pk) and status is changing to CANCELLED from PAID
        if self.pk:
            try:
                original = Invoice.objects.get(pk=self.pk)
                
                # If transitioning from PAID to CANCELLED
                if original.status == self.Status.PAID and self.status == self.Status.CANCELLED:
                    # Validate: payment should never exceed invoice amount
                    if self.total_paid > self.total_amount:
                        raise ValidationError(
                            f"Cannot cancel invoice: Payment ({self.user.profile.currency} {self.total_paid}) "
                            f"exceeds invoice amount ({self.user.profile.currency} {self.total_amount}). "
                            f"This is a data integrity error."
                        )
            except Invoice.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        """
        Enhanced save with business rules:
        1. Validate data integrity
        2. Auto-create credit note when PAID invoice is cancelled
        """
        # Only run full validation if NOT doing an internal field update
        # (update_fields is used by manager's update_totals for calculated fields)
        if not kwargs.get("update_fields"):
            self.full_clean()
        
        # Check if this is a status change from PAID to CANCELLED
        credit_note_created = False
        if self.pk and not kwargs.get("update_fields"):
            try:
                original = Invoice.objects.get(pk=self.pk)
                
                if original.status == self.Status.PAID and self.status == self.Status.CANCELLED:
                    # Auto-create a credit note for the paid amount
                    from django.db import transaction
                    
                    with transaction.atomic():
                        # Call parent save first
                        super().save(*args, **kwargs)
                        
                        # Create credit note for the paid amount
                        paid_amount = original.total_paid
                        if paid_amount > Decimal("0.00"):
                            CreditNote.objects.create(
                                user=self.user,
                                client=self.client,
                                invoice=self,
                                note_type=CreditNote.NoteType.CANCELLATION,
                                amount=paid_amount,
                                description=f"Credit from cancelled invoice {self.number}. Reason: {self.cancellation_reason or 'No reason provided'}",
                                reference=f"CN-{self.number}"
                            )
                            credit_note_created = True
                    
                    if credit_note_created:
                        return
            except Invoice.DoesNotExist:
                pass
        
        # Normal save for all other cases
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.number or 'DRAFT'} - {self.client.name}"


class Payment(TenantModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    credit_applied = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_paid = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True, null=True)  # Ensure blank=True is here

    objects = PaymentManager()

    #    def clean(self):
    #        super().clean()
    #        if self.invoice.status == 'DRAFT':
    #            raise ValidationError(
    #                "Cannot add a payment to a 'Draft' invoice. "
    #                "Please mark the invoice as 'Sent' or 'Pending' first."
    #        )

    # def clean(self):
    #     super().clean()
    #     if self.invoice.status == 'DRAFT':
    #         raise ValidationError(
    #             "Cannot add a payment to a 'Draft' invoice. "
    #             "Please mark the invoice as 'Sent' or 'Pending' first.",
    #             line_errors=[]  # Satisfies the required argument
    #    )

    def clean(self):
        super().clean()
        if self.invoice.status == "DRAFT":
            raise ValidationError("Cannot add a payment to a 'Draft' invoice.")

        # RULE 1: No payments on CANCELLED invoices
        if self.invoice.status == "CANCELLED":
            raise ValidationError("Cannot add a payment to a 'Cancelled' invoice.")

        # RULE 2: Payment + existing payments must not exceed total invoice amount
        # This is the hardest rule - payment should never exceed (invoice total - other payments)
        existing_paid = sum(
            Decimal(str(p.amount + p.credit_applied)) 
            for p in self.invoice.payments.exclude(pk=self.pk)
        )
        total_would_be = existing_paid + self.amount + self.credit_applied
        
        if total_would_be > self.invoice.total_amount:
            currency = self.user.profile.currency
            raise ValidationError(
                f"Payment would cause total paid ({currency} {total_would_be}) to exceed "
                f"invoice amount ({currency} {self.invoice.total_amount}). "
                f"Current total paid: {currency} {existing_paid}, "
                f"this payment: {currency} {self.amount + self.credit_applied}"
            )

        # RULE 3: Check individual cash payment doesn't exceed balance
        if self.amount > self.invoice.balance_due:
            currency = self.user.profile.currency
            raise ValidationError(
                f"Cash payment amount ({currency} {self.amount}) cannot exceed the "
                f"balance due ({currency} {self.invoice.balance_due})"
            )

        # RULE 4: Allow amount=0 for credit-only payments, but not negative
        if self.amount < 0:
            raise ValidationError("Payment amount cannot be negative")
        
        # RULE 5: Credit applied should not be negative
        if self.credit_applied < 0:
            raise ValidationError("Credit applied cannot be negative")

    # invoices/models.py (Payment)

    def save(self, *args, **kwargs):
        # 1. Run the validation (clean)
        self.full_clean()

        with transaction.atomic():
            super().save(*args, **kwargs)

        # 2. Use the Manager to refresh the status
        # This is cleaner than calling self.invoice.save()
        Invoice.objects.update_totals(self.invoice)

    def __str__(self):
        return f"{self.user.profile.currency} {self.amount} for {self.invoice.number}"


class CreditNote(TenantModel):
    """
    Tracks credit notes issued to clients for:
    - Overpayments (when payment exceeded invoice due)
    - Manual adjustments/discounts
    - Corrections to cancelled invoices

    Can be applied against future invoices as a credit.
    """

    class NoteType(models.TextChoices):
        OVERPAYMENT = "OVERPAYMENT", "Overpayment"
        ADJUSTMENT = "ADJUSTMENT", "Manual Adjustment"
        CANCELLATION = "CANCELLATION", "Cancelled Invoice"
        OTHER = "OTHER", "Other"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="credit_notes")
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_notes",
        help_text="Original invoice if related to overpayment/cancellation",
    )

    note_type = models.CharField(max_length=20, choices=NoteType.choices, default=NoteType.ADJUSTMENT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, help_text="Reason for credit note")
    reference = models.CharField(max_length=100, blank=True, help_text="e.g., CN2026-001")

    issued_date = models.DateField(default=timezone.now)
    balance = models.DecimalField(max_digits=12, decimal_places=2, help_text="Remaining credit available to use")

    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CreditNoteManager()

    class Meta:
        ordering = ["-issued_date", "-created_at"]

    def save(self, *args, **kwargs):
        if not self.balance:
            self.balance = self.amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"CN - {self.client.name} - {self.user.profile.currency} {self.amount} ({self.issued_date})"


class Coupon(TenantModel):
    """
    Promotional coupons that provide discounts on invoices.
    Can be fixed amount or percentage-based.
    Can be applied multiple times until expiry or usage limit reached.
    """

    class DiscountType(models.TextChoices):
        FIXED = "FIXED", "Fixed Amount"
        PERCENTAGE = "PERCENTAGE", "Percentage Discount"

    code = models.CharField(max_length=50, help_text="e.g., SUMMER2026, LOYAL10")
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, default=DiscountType.FIXED)
    discount_value = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Fixed amount or percentage (e.g., 10.00 for 10% or R500)"
    )

    description = models.TextField(blank=True, help_text="Coupon description for internal use")

    # Usage tracking
    max_uses = models.IntegerField(null=True, blank=True, help_text="Unlimited if blank")
    current_uses = models.IntegerField(default=0, help_text="Number of times coupon has been used")

    # Validity
    valid_from = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True, help_text="Null = no expiry")
    is_active = models.BooleanField(default=True)

    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("user", "code")

    def is_valid(self):
        """Check if coupon is currently valid."""
        today = timezone.now().date()
        if not self.is_active:
            return False
        if today < self.valid_from:
            return False
        if self.valid_until and today > self.valid_until:
            return False
        if self.max_uses and self.current_uses >= self.max_uses:
            return False
        return True

    def apply_discount(self, invoice_amount):
        """Calculate discount amount based on type."""
        if self.discount_type == self.DiscountType.FIXED:
            return min(self.discount_value, invoice_amount)
        else:  # PERCENTAGE
            return (invoice_amount * self.discount_value) / Decimal("100")

    def use(self):
        """Mark coupon as used."""
        self.current_uses += 1
        self.save()

    def __str__(self):
        discount_str = (
            f"{self.discount_value}%"
            if self.discount_type == self.DiscountType.PERCENTAGE
            else f"{self.user.profile.currency}{self.discount_value}"
        )
        return f"{self.code} - {discount_str}"


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
        unique_together = ("user", "month", "year")
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"VAT Report {self.year}-{self.month:02d} ({self.user.username})"


class TaxPayment(TenantModel):
    payment_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., VAT201 Period 2026/01. Leave blank for auto-generated reference.")  # noqa: E501
    tax_type = models.CharField(max_length=20, default="VAT", choices=[("VAT", "VAT"), ("INCOME_TAX", "Income Tax")])

    def __str__(self):
        return f"{self.tax_type} Payment - {self.user.profile.currency} {self.amount} ({self.payment_date})"  # noqa: E501
