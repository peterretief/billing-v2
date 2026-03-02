# Critical Bug Fixes - Code Solutions

This document provides specific code fixes for the highest-priority bugs identified in the analysis.

---

## Fix #1: Payment Validation Logic Error

**File:** `invoices/models.py` (Payment.clean() method, ~line 340)

**Current Code (BUGGY):**
```python
def clean(self):
    super().clean()
    if self.invoice.status == "DRAFT":
        raise ValidationError("Cannot add a payment to a 'Draft' invoice.")

    if self.invoice.status == "CANCELLED":
        raise ValidationError("Cannot add a payment to a 'Cancelled' invoice.")

    existing_paid = sum(
        Decimal(str(p.amount + p.credit_applied)) 
        for p in self.invoice.payments.exclude(pk=self.pk)  # BUG: For new payments, pk=None, so exclude(pk=None) doesn't exclude anything
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
```

**Fixed Code:**
```python
def clean(self):
    super().clean()
    if self.invoice.status == "DRAFT":
        raise ValidationError("Cannot add a payment to a 'Draft' invoice.")

    if self.invoice.status == "CANCELLED":
        raise ValidationError("Cannot add a payment to a 'Cancelled' invoice.")

    # FIXED: Properly exclude current payment
    existing_paid = Decimal("0.00")
    for p in self.invoice.payments.all():
        if p.pk != self.pk:  # Skip current payment (None for new payments too)
            existing_paid += Decimal(str(p.amount + p.credit_applied))
    
    total_would_be = existing_paid + self.amount + self.credit_applied
    
    if total_would_be > self.invoice.total_amount:
        currency = self.user.profile.currency
        raise ValidationError(
            f"Payment would cause total paid ({currency} {total_would_be}) to exceed "
            f"invoice amount ({currency} {self.invoice.total_amount}). "
            f"Current total paid: {currency} {existing_paid}, "
            f"this payment: {currency} {self.amount + self.credit_applied}"
        )
```

---

## Fix #2: Transaction Handling & Return Logic

**File:** `invoices/models.py` (Invoice.save() method, ~line 258)

**Current Code (BUGGY):**
```python
def save(self, *args, **kwargs):
    if not kwargs.get("update_fields"):
        self.full_clean()
    
    credit_note_created = False
    if self.pk and not kwargs.get("update_fields"):
        try:
            original = Invoice.objects.get(pk=self.pk)
            
            if original.status == self.Status.PAID and self.status == self.Status.CANCELLED:
                from django.db import transaction
                
                with transaction.atomic():
                    super().save(*args, **kwargs)
                    
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
                    return  # BUG: Early return, but normal save might not have run!
        except Invoice.DoesNotExist:
            pass
    
    super().save(*args, **kwargs)
```

**Fixed Code:**
```python
def save(self, *args, **kwargs):
    if not kwargs.get("update_fields"):
        self.full_clean()
    
    # Check if this is a status change from PAID to CANCELLED
    if self.pk and not kwargs.get("update_fields"):
        try:
            original = Invoice.objects.get(pk=self.pk)
            
            if original.status == self.Status.PAID and self.status == self.Status.CANCELLED:
                with transaction.atomic():
                    # Save the invoice first
                    super().save(*args, **kwargs)
                    
                    # Then create credit note for the paid amount
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
                    # Complete - transaction will commit here
                return
        except Invoice.DoesNotExist:
            pass
    
    # Normal save for all other cases
    super().save(*args, **kwargs)
```

---

## Fix #3: Float Conversion for Financial Data

**File:** `invoices/views.py` (~lines 440, 507, 624)

**Current Code (BUGGY):**
```python
BillingAuditLog.objects.create(
    user=request.user,
    invoice=invoice,
    is_anomaly=is_anomaly,
    ai_comment=comment,
    details={"total": float(invoice.total_amount), "source": "manual_create"},  # BUG: float loses precision
)
```

**Fixed Code:**
```python
# Option 1: Use string representation (preserves all decimal places)
BillingAuditLog.objects.create(
    user=request.user,
    invoice=invoice,
    is_anomaly=is_anomaly,
    ai_comment=comment,
    details={"total": str(invoice.total_amount), "source": "manual_create"},
)

# Option 2: Use json.JSONEncoder if you have custom Decimal encoder (better for JSON)
from django.core.serializers.json import DjangoJSONEncoder
import json

details_json = json.dumps(
    {"total": invoice.total_amount, "source": "manual_create"},
    cls=DjangoJSONEncoder
)
BillingAuditLog.objects.create(
    user=request.user,
    invoice=invoice,
    is_anomaly=is_anomaly,
    ai_comment=comment,
    details=json.loads(details_json),
)
```

---

## Fix #4: UserProfile Access Guard

**File:** `invoices/models.py` (calculated_vat property, ~line 195)

**Current Code (BUGGY):**
```python
@property
def calculated_vat(self):
    from decimal import Decimal

    try:
        is_registered = self.user.profile.is_vat_registered  # Crashes if profile doesn't exist
        rate = self.user.profile.vat_rate / Decimal(100)  # Also doesn't guard against None vat_rate
    except (AttributeError, TypeError):
        is_registered = False
        rate = Decimal("0.00")

    if not is_registered:
        return Decimal("0.00")

    return (self.calculated_subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

**Fixed Code:**
```python
@property
def calculated_vat(self):
    from decimal import Decimal

    # Safely get profile
    profile = getattr(self.user, 'profile', None)
    if not profile:
        return Decimal("0.00")

    # Get VAT settings with defaults
    is_registered = getattr(profile, 'is_vat_registered', False)
    if not is_registered:
        return Decimal("0.00")

    # Get rate with safe default
    vat_rate = getattr(profile, 'vat_rate', None)
    if vat_rate is None or vat_rate < 0:
        vat_rate = Decimal("15.00")
    
    # Calculate VAT
    rate = vat_rate / Decimal(100)
    return (self.calculated_subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

---

## Fix #5: Decimal Zero Comparison

**File:** `invoices/managers.py` (update_totals method, ~line 144)

**Current Code (BUGGY):**
```python
custom_vat_rate = getattr(profile, "vat_rate", None) or Decimal("15.00")
# BUG: If vat_rate is legitimately Decimal("0.00"), it becomes Decimal("15.00")
```

**Fixed Code:**
```python
custom_vat_rate = getattr(profile, "vat_rate", None)
if custom_vat_rate is None:
    custom_vat_rate = Decimal("15.00")
# Now Decimal("0.00") is preserved correctly
```

---

## Fix #6: N+1 Query in invoice_list

**File:** `invoices/views.py` (invoice_list view, ~line 302)

**Current Code (BUGGY):**
```python
invoice_queryset = (
    Invoice.objects.filter(user=request.user)
    .select_related("client")
    .prefetch_related(
        Prefetch(
            "delivery_logs",
            queryset=InvoiceEmailStatusLog.objects.order_by("-created_at"),
        )
    )
    .annotate(...)
)

# ... later in view ...
for invoice in page_obj:
    invoice.latest_delivery_status = invoice.get_latest_delivery_status()  # N additional queries!
```

**Fixed Code:**
```python
# Option 1: Cache in the loop
invoice_queryset = (
    Invoice.objects.filter(user=request.user)
    .select_related("client")
    .prefetch_related(
        Prefetch(
            "delivery_logs",
            queryset=InvoiceEmailStatusLog.objects.order_by("-created_at"),
        )
    )
    .annotate(...)
)

# ... later in view ...
for invoice in page_obj:
    # Use prefetched delivery_logs directly
    logs = list(invoice.delivery_logs.all())
    if logs:
        priority = {"DELIVERED": 3, "SENT": 2, "REQUEST": 1}
        logs.sort(key=lambda l: (priority.get(l.status.upper(), 0), l.created_at), reverse=True)
        invoice.latest_delivery_status = logs[0].status
    else:
        invoice.latest_delivery_status = None

# Option 2: Add annotation to queryset (best)
from django.db.models import Window, F
from django.db.models.functions import Row

invoice_queryset = (
    Invoice.objects.filter(user=request.user)
    .select_related("client")
    .prefetch_related("delivery_logs")
    .annotate(...)
    .annotate(
        latest_delivery_status=Window(
            expression=FirstValue("delivery_logs__status"),
            partition_by=[F("pk")],
            order_by=F("delivery_logs__created_at").desc()
        )
    )
)
```

---

## Fix #7: Division by Zero in Revenue Target

**File:** `invoices/managers.py` (get_revenue_vs_target, ~line 409)

**Current Code (BUGGY):**
```python
def get_revenue_vs_target(self, user):
    ytd = self.get_ytd_revenue(user)
    profile = user.profile
    annual_target = profile.get_annual_revenue_target()
    
    remaining = annual_target - ytd
    percent_complete = (ytd / annual_target * 100) if annual_target > 0 else 0
    
    # ... rest
```

**Fixed Code:**
```python
def get_revenue_vs_target(self, user):
    ytd = self.get_ytd_revenue(user)
    profile = user.profile
    annual_target = profile.get_annual_revenue_target()
    
    # Guard against zero or negative target
    if annual_target <= 0:
        return {
            "ytd_revenue": ytd,
            "annual_target": Decimal("0.00"),
            "remaining": Decimal("0.00"),
            "percent_complete": Decimal("0.00"),
            "on_track": None,  # Unknown - no target set
            "status_message": "No annual target configured"
        }
    
    remaining = annual_target - ytd
    percent_complete = min((ytd / annual_target * 100), Decimal("100.00"))  # Cap at 100%
    
    # Pro-rata check: have we earned the expected amount for this day of the year?
    today = timezone.now().date()
    day_of_year = Decimal(str(today.timetuple().tm_yday))
    expected_by_today = annual_target * (day_of_year / Decimal("365.25"))
    on_track = ytd >= expected_by_today
    
    return {
        "ytd_revenue": ytd,
        "annual_target": annual_target,
        "remaining": max(remaining, Decimal("0.00")),  # Never negative
        "percent_complete": percent_complete,
        "on_track": on_track,
    }
```

---

## Fix #8: Add Database Indexes for Performance

**File:** `invoices/models.py` (Invoice model definition, ~line 112)

**Current Code (MISSING INDEXES):**
```python
class Invoice(TenantModel):
    # ... other fields ...
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    is_quote = models.BooleanField(default=False, db_index=True)
    date_issued = models.DateField(default=date.today)
    # ... missing indexes on frequently queried fields
```

**Fixed Code:**
```python
class Invoice(TenantModel):
    # ... other fields ...
    status = models.CharField(
        max_length=10, 
        choices=Status.choices, 
        default=Status.DRAFT,
        db_index=True  # ADD THIS
    )
    is_quote = models.BooleanField(default=False, db_index=True)  # Already has it
    date_issued = models.DateField(
        default=date.today,
        db_index=True  # ADD THIS
    )
    is_emailed = models.BooleanField(default=False, db_index=True)  # ADD THIS
    is_template = models.BooleanField(
        default=False,
        db_index=True,  # Already has it
        help_text="If checked, this invoice will be used as a base for recurring monthly billing.",
    )
    
    # ADD COMPOSITE INDEX for common filter patterns
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "number"], name="unique_invoice_per_tenant"),
            models.Index(fields=["user", "status", "date_issued"], name="idx_invoice_user_status_date"),
            models.Index(fields=["user", "is_quote", "status"], name="idx_invoice_user_quote_status"),
        ]
```

Then create migration:
```bash
python manage.py makemigrations
python manage.py migrate
```

---

## Fix #9: Auto-Sync Invoice Status on View Access

**File:** `invoices/views.py` OR create new `invoices/signals.py`

**Option 1: In View (Quick Fix):**
```python
@login_required
@setup_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    # Auto-fix orphaned invoices (have delivery logs but wrong status)
    if invoice.sync_status_with_delivery():
        invoice.refresh_from_db()  # Reload after sync
    return render(request, "invoices/invoice_detail.html", {"invoice": invoice})
```

**Option 2: Using Signal (Better):**
```python
# In invoices/signals.py (add if doesn't exist)
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Invoice

@receiver(post_save, sender=Invoice)
def auto_sync_invoice_status(sender, instance, **kwargs):
    """
    Auto-sync invoice status based on delivery logs.
    If invoice has delivery logs showing "sent" or "delivered" but is still DRAFT,
    move it to PENDING to recover from orphaned state.
    """
    if instance.status == Invoice.Status.DRAFT:
        if instance.delivery_logs.filter(status__in=["sent", "delivered"]).exists():
            instance.status = Invoice.Status.PENDING
            instance.is_emailed = True
            if not instance.emailed_at:
                from django.utils import timezone
                instance.emailed_at = timezone.now()
            # Use update to avoid recursive signal
            Invoice.objects.filter(pk=instance.pk).update(
                status=instance.status,
                is_emailed=instance.is_emailed,
                emailed_at=instance.emailed_at
            )

# In invoices/apps.py
class InvoicesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invoices'
    
    def ready(self):
        import invoices.signals  # Import signals when app loads
```

---

## Fix #10: Better Credit Note Balance Management

**File:** `invoices/models.py` (CreditNote model)

**Current Code (ALLOWS NEGATIVE BALANCE):**
```python
class CreditNote(TenantModel):
    # ... other fields ...
    balance = models.DecimalField(max_digits=12, decimal_places=2, 
                                 help_text="Remaining credit available to use")
```

**Fixed Code:**
```python
class CreditNote(TenantModel):
    # ... other fields ...
    balance = models.DecimalField(max_digits=12, decimal_places=2, 
                                 help_text="Remaining credit available to use")
    is_active = models.BooleanField(default=True, db_index=True)  # Track if used
    
    def save(self, *args, **kwargs):
        if not self.balance:
            self.balance = self.amount
        
        # Ensure balance is never negative
        if self.balance < 0:
            self.balance = Decimal("0.00")
        
        # Auto-deactivate if fully used
        if self.balance <= 0:
            self.is_active = False
        
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ["-issued_date", "-created_at"]
        constraints = [
            # Ensure balance is never negative
            models.CheckConstraint(
                check=models.Q(balance__gte=0),
                name='credit_note_balance_non_negative'
            ),
            # Ensure balance doesn't exceed amount
            models.CheckConstraint(
                check=models.Q(balance__lte=models.F('amount')),
                name='credit_note_balance_lte_amount'
            ),
        ]
```

Then update views to use soft-delete:
```python
# In invoices/views.py, record_payment function
for credit_note in available_credits:
    if remaining_to_apply <= 0:
        break

    amount_to_use = min(remaining_to_apply, credit_note.balance)
    credit_note.balance -= amount_to_use

    if credit_note.balance <= 0:
        credit_note.is_active = False  # Soft delete instead of hard delete
    
    credit_note.save()  # This triggers constraints check
    credits_used += amount_to_use
    remaining_to_apply -= amount_to_use
```

---

## Testing Code to Verify Fixes

```python
# tests/test_critical_fixes.py
from decimal import Decimal
from django.test import TestCase
from invoices.models import Invoice, Payment, CreditNote
from clients.models import Client

class PaymentValidationFixTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test', email='test@test.com')
        self.client = Client.objects.create(user=self.user, name='Test Client', email='client@test.com')
        self.invoice = Invoice.objects.create(
            user=self.user, 
            client=self.client, 
            total_amount=Decimal("1000.00"),
            status="PENDING"
        )

    def test_new_payment_validation_with_existing_payments(self):
        """Test that new payments don't double-count existing payments"""
        # Create first payment
        Payment.objects.create(
            user=self.user,
            invoice=self.invoice,
            amount=Decimal("400.00")
        )
        
        # Try to create second payment that would exceed total
        payment2 = Payment(
            user=self.user,
            invoice=self.invoice,
            amount=Decimal("700.00")  # 400 + 700 = 1100 > 1000
        )
        
        with self.assertRaises(ValidationError) as ctx:
            payment2.full_clean()
        
        self.assertIn("exceed", str(ctx.exception))

    def test_decimal_zero_vat_not_replaced(self):
        """Test that 0% VAT is not replaced with default 15%"""
        profile = self.user.profile
        profile.is_vat_registered = True
        profile.vat_rate = Decimal("0.00")  # Some countries have 0% VAT
        profile.save()
        
        self.invoice.subtotal_amount = Decimal("1000.00")
        invoice.calculated_vat == Decimal("0.00")  # Should be 0, not 150
        
    def test_credit_note_balance_non_negative(self):
        """Test that credit note balance can't go below zero"""
        credit = CreditNote.objects.create(
            user=self.user,
            client=self.client,
            amount=Decimal("500.00")
        )
        
        # Manually set balance to negative (shouldn't be possible after fix)
        credit.balance = Decimal("-10.00")
        credit.save()  # Model should prevent this
        
        # Reload and check
        credit.refresh_from_db()
        self.assertGreaterEqual(credit.balance, Decimal("0.00"))
```

---

## Deployment Checklist

Before deploying these fixes:

- [ ] Run all existing tests: `python manage.py test`
- [ ] Run new test code above: `python manage.py test tests.test_critical_fixes`
- [ ] Create database migration for indexes (Fix #8)
- [ ] Create database migration for credit note constraints (Fix #10)
- [ ] Deploy migration: `python manage.py migrate`
- [ ] Deploy code changes
- [ ] Monitor error logs for 24 hours
- [ ] Run reconciliation reports to verify data integrity

