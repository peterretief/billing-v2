# Django Billing Application - Bug Analysis Report
**Analysis Date:** March 2, 2026  
**Scope:** invoices, core, billing_schedule, and clients modules

---

## Critical Issues (HIGH SEVERITY)

### 1. **Type Mismatch: Float Conversion for Financial Data** 
**File:** [invoices/views.py](invoices/views.py#L440) (Lines 440, 507, 624)  
**Severity:** HIGH  
**Issue:** Using `float(invoice.total_amount)` to store financial data in audit logs:
```python
details={"total": float(invoice.total_amount), "source": "manual_create"}
```
**Problem:** 
- Floats have precision issues (e.g., 0.1 + 0.2 ≠ 0.3 in binary floating-point)
- Audit records lose precision for financial amounts
- Makes accounting reconciliation impossible

**Suggested Fix:**
```python
details={"total": str(invoice.total_amount), "source": "manual_create"}  # or use Decimal serialization
```

---

### 2. **Payment Validation Logic Error**
**File:** [invoices/models.py](invoices/models.py#L340-L365)  
**Severity:** HIGH  
**Issue:** In `Payment.clean()`, the calculation of `existing_paid` doesn't exclude the current payment properly:
```python
existing_paid = sum(
    Decimal(str(p.amount + p.credit_applied)) 
    for p in self.invoice.payments.exclude(pk=self.pk)  # OK for edit, but...
)
```
**Problem:**
- When creating a NEW payment (pk=None), `self.pk` is None, so `.exclude(pk=None)` does nothing
- This means for new payments, it's summing ALL existing payments twice (existing + this one)
- Can allow payments to exceed invoice amount on first payment entry

**Suggested Fix:**
```python
# For new payments (no pk yet), exclude nothing. For edits, exclude self.
existing_paid = sum(
    Decimal(str(p.amount + p.credit_applied)) 
    for p in self.invoice.payments.all() if p.pk != self.pk
)
```

---

### 3. **Transaction Handling & Return Logic Error**
**File:** [invoices/models.py](invoices/models.py#L260-L300)  
**Severity:** HIGH  
**Issue:** In `Invoice.save()`, early return after creating credit note causes incomplete save:
```python
with transaction.atomic():
    super().save(*args, **kwargs)
    CreditNote.objects.create(...)
    credit_note_created = True

if credit_note_created:
    return  # EARLY RETURN - skips the normal save at the end!
```
**Problem:**
- If credit note is created, the function returns early and never executes the normal `super().save()`
- Invoice changes from the `full_clean()` validation are saved (line 281), but any other changes are not
- Potential state inconsistency

**Suggested Fix:**
```python
if original.status == self.Status.PAID and self.status == self.Status.CANCELLED:
    with transaction.atomic():
        super().save(*args, **kwargs)  # Save invoice first
        paid_amount = original.total_paid
        if paid_amount > Decimal("0.00"):
            CreditNote.objects.create(...)
    return  # Now return is OK - everything was saved

# Normal save for all other cases
super().save(*args, **kwargs)
```

---

## Data Integrity Issues (HIGH SEVERITY)

### 4. **Unsafe UserProfile Access Pattern**
**File:** [invoices/views.py](invoices/views.py#L175), [invoices/models.py](invoices/models.py#L197), multiple  
**Severity:** HIGH  
**Issue:** Accessing `request.user.profile` without always checking if it exists:
```python
currency = request.user.profile.currency if hasattr(request.user, "profile") else "R"  # Good
is_registered = self.user.profile.is_vat_registered  # Dangerous!
```
**Problem:**
- Profile is OneToOneField and can theoretically be deleted
- If profile deleted, accessing `.profile` raises ObjectDoesNotExist, crashing views
- Inconsistent error handling across codebase

**Suggested Fix:**
Wrap all profile access in try-except or use `getattr()`:
```python
@property
def calculated_vat(self):
    profile = getattr(self.user, 'profile', None)
    if not profile:
        return Decimal("0.00")
    try:
        is_registered = profile.is_vat_registered
        rate = profile.vat_rate / Decimal(100)
    except (AttributeError, TypeError):
        return Decimal("0.00")
    
    if not is_registered:
        return Decimal("0.00")
    
    return (self.calculated_subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

---

## Performance Issues (MEDIUM SEVERITY)

### 5. **N+1 Query Problem in invoice_list**
**File:** [invoices/views.py](invoices/views.py#L372)  
**Severity:** MEDIUM  
**Issue:** Calling method in a loop that queries database:
```python
for invoice in page_obj:
    invoice.latest_delivery_status = invoice.get_latest_delivery_status()  # N queries!
```
**Problem:**
- `get_latest_delivery_status()` calls `self.delivery_logs.all()` (line 45)
- For 5 invoices on page, this is 5 additional queries
- Should use prefetch_related instead

**Suggested Fix:**
```python
# In query setup:
invoice_queryset = (
    Invoice.objects.filter(user=request.user)
    .select_related("client")
    .prefetch_related("delivery_logs")  # Add this
    .annotate(...)
)

# Then in template or view, access delivery_logs directly without calling method
# OR modify get_latest_delivery_status() to not query if prefetched
```

---

### 6. **Missing prefetch_related for Dashboard Card Calculations**
**File:** [invoices/views.py](invoices/views.py#L206-L250)  
**Severity:** MEDIUM  
**Issue:** Multiple independent queries on related models:
```python
invoices = Invoice.objects.filter(user=request.user).select_related("client")
unbilled_ts = TimesheetEntry.objects.filter(user=request.user, is_billed=False).aggregate(...)
unbilled_items = Item.objects.filter(...).aggregate(...)
# ... Many more separate queries
```
**Problem:**
- Each aggregate call is a separate database query
- Dashboard loads 15+ separate queries (N+1 pattern at view level)
- Slow page load for users with many line items

**Suggested Fix:**
Batch aggregate queries or use a single complex query with annotations.

---

### 7. **Dashboard Doesn't select_related UserProfile**
**File:** [invoices/views.py](invoices/views.py#L299)  
**Severity:** MEDIUM  
**Issue:** Dashboard accesses `request.user.profile` multiple times without prefetching:
```python
# In managers.py methods like get_revenue_vs_target(), get_tax_summary(), etc.
profile = user.profile  # New query each time a manager method is called
annual_target = profile.get_annual_revenue_target()  # May query again
```
**Problem:**
- If dashboard calls 5+ manager methods, each might query profile
- Moving profile access to view setup would cache it

**Suggested Fix:**
```python
# In dashboard view, prefetch once:
request.user = User.objects.select_related('profile').get(pk=request.user.pk)
# or use django.dispatch caching
```

---

## Logic Errors (MEDIUM SEVERITY)

### 8. **Division by Zero in Revenue Tracking**
**File:** [invoices/managers.py](invoices/managers.py#L410-L430)  
**Severity:** MEDIUM  
**Issue:** Potential division by zero when calculating `on_track`:
```python
def get_revenue_vs_target(self, user):
    annual_target = profile.get_annual_revenue_target()
    # ...
    percent_complete = (ytd / annual_target * 100) if annual_target > 0 else 0
    
    day_of_year = Decimal(str(today.timetuple().tm_yday))
    expected_by_today = annual_target * (day_of_year / Decimal("365.25"))
    on_track = ytd >= expected_by_today  # OK here
```
**Problem:**
- While division is guarded, if `annual_target` is 0, expected_by_today = 0
- Users with $0 target will always be marked "on_track", which is misleading

**Suggested Fix:**
```python
def get_revenue_vs_target(self, user):
    annual_target = profile.get_annual_revenue_target()
    if annual_target <= 0:
        return {
            "ytd_revenue": ytd,
            "annual_target": Decimal("0.00"),
            "remaining": Decimal("0.00"),
            "percent_complete": Decimal("0.00"),
            "on_track": None,  # Unknown - no target set
        }
    # ... rest of calculation
```

---

### 9. **Incorrect Null Coalescing in Managers**
**File:** [invoices/managers.py](invoices/managers.py#L139-L150)  
**Severity:** MEDIUM  
**Issue:** Using `or` operator on Decimal which could be zero:
```python
custom_vat_rate = getattr(profile, "vat_rate", None) or Decimal("15.00")
```
**Problem:**
- If `vat_rate` is legitimately `Decimal("0.00")` (0% VAT), it will be replaced with default 15%
- `0 or 15` evaluates to 15, causing data corruption

**Suggested Fix:**
```python
custom_vat_rate = getattr(profile, "vat_rate", None)
if custom_vat_rate is None:
    custom_vat_rate = Decimal("15.00")
```

---

### 10. **Budget Calculation with Mixed Data Types**
**File:** [invoices/managers.py](invoices/managers.py#L490-510)  
**Severity:** MEDIUM  
**Issue:** In `get_quarterly_report()`, summing in Python instead of database:
```python
q_invoices = self.filter(
    user=user,
    is_quote=False,
    date_issued__gte=q_start,
    date_issued__lte=q_end
).exclude(status='CANCELLED')

q_revenue = sum(
    (inv.subtotal_amount + inv.tax_amount) for inv in q_invoices  # Python loop!
)
```
**Problem:**
- Loads all invoices into memory and sums in Python
- For users with thousands of invoices, this is very slow
- Decimal arithmetic in Python is slower than SQL

**Suggested Fix:**
```python
q_invoice = self.filter(
    user=user,
    is_quote=False,
    date_issued__gte=q_start,
    date_issued__lte=q_end,
    status__in=['PENDING', 'PAID', 'OVERDUE']  # More specific filter
).aggregate(
    total=Coalesce(Sum(F('subtotal_amount') + F('tax_amount')), Decimal('0.00'))
)
q_revenue = q_invoice['total']
```

---

## Validation Issues (MEDIUM SEVERITY)

### 11. **Missing Form Validation for Credit Notes**
**File:** [invoices/forms.py](invoices/forms.py#L121-141)  
**Severity:** MEDIUM  
**Issue:** Form validation doesn't check if credit amount exceeds overpayment on invoice:
```python
def clean(self):
    # Validates amount > 0 and client exists
    # BUT does NOT validate:
    # - Credit note amount doesn't exceed invoice balance
    # - If it's an overpayment credit, it's not larger than paid amount
```
**Problem:**
- User can create unlimited credit notes without reference to invoice
- No business rule enforcement at form level

**Suggested Fix:**
```python
def clean(self):
    cleaned_data = super().clean()
    amount = cleaned_data.get("amount")
    invoice = cleaned_data.get("invoice")
    note_type = cleaned_data.get("note_type")
    
    if note_type == "OVERPAYMENT" and invoice:
        if amount > invoice.total_paid:
            self.add_error("amount", f"Credit cannot exceed payments on invoice ({self.user.profile.currency}{invoice.total_paid})")
    
    return cleaned_data
```

---

### 12. **VATPaymentForm Allows $0 Reference**
**File:** [invoices/forms.py](invoices/forms.py#L28-39)  
**Severity:** MEDIUM  
**Issue:** Reference field returns `None` instead of auto-generating:
```python
def clean_reference(self):
    reference = self.cleaned_data.get("reference")
    if reference:
        return reference.strip()
    return None  # Stores None in database
```
**Problem:**
- TaxPayment.reference is blank=True but doesn't auto-generate
- Unclear which payment corresponds to which tax period
- Historical audit trail becomes unlinked

**Suggested Fix:**
```python
def clean_reference(self):
    reference = self.cleaned_data.get("reference")
    if reference:
        return reference.strip()
    # Auto-generate if blank
    payment_date = self.cleaned_data.get('payment_date') or timezone.now().date()
    return f"VAT{payment_date.year % 100:02d}{payment_date.strftime('%b').upper()}"
```

---

## Data Consistency Issues (MEDIUM SEVERITY)

### 13. **No Guarantee of Invoice Status Sync on Email**
**File:** [invoices/models.py](invoices/models.py#L56-96)  
**Severity:** MEDIUM  
**Issue:** `can_record_payment()` and `sync_status_with_delivery()` only called manually:
```python
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    invoice.sync_status_with_delivery()  # Manual call required!
```
**Problem:**
- If invoice doesn't go through invoice_detail view, status stays stale
- Orphaned invoices (sent but marked DRAFT) can exist
- No automatic recovery mechanism

**Suggested Fix:**
Add a model signal or middleware to auto-sync:
```python
@receiver(post_save, sender=Invoice)
def auto_sync_invoice_status(sender, instance, **kwargs):
    """Auto-sync invoice status with delivery logs periodically"""
    if instance.status == "DRAFT" and instance.delivery_logs.filter(status__in=["sent", "delivered"]).exists():
        instance.status = "PENDING"
        instance.is_emailed = True
        instance.save(update_fields=['status', 'is_emailed'])
```

---

### 14. **No Constraint on CreditNote.balance**
**File:** [invoices/models.py](invoices/models.py#L473)  
**Severity:** MEDIUM  
**Issue:** CreditNote.balance can be negative:
```python
# No validation in model
balance = models.DecimalField(max_digits=12, decimal_places=2)
```
**Problem:**
- In `record_payment()` view, balance is decremented without min check
- Can end up with negative credit balances
- Breaks accounting logic

**Suggested Fix:**
```python
# Add a constraint in model Meta:
class Meta:
    constraints = [
        models.CheckConstraint(
            check=models.Q(balance__gte=0),
            name='credit_note_balance_non_negative'
        )
    ]

# Or add validation in save():
def save(self, *args, **kwargs):
    if self.balance < 0:
        self.balance = Decimal("0.00")
    super().save(*args, **kwargs)
```

---

### 15. **Missing Uniqueness Constraint on Invoice Numbers**
**File:** [invoices/models.py](invoices/models.py#L177-182)  
**Severity:** MEDIUM  
**Issue:** While there's a unique constraint, it's on (user, number):
```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=["user", "number"], name="unique_invoice_per_tenant")
    ]
```
**Problem:**
- Blank/auto-generated numbers can duplicate across invoices
- Multiple invoices can have empty number field (multiple NULLs allowed)
- Number generation in signals could fail silently

**Suggested Fix:**
Ensure number is always filled before constraint check:
```python
def save(self, *args, **kwargs):
    if not self.number:
        # Generate here instead of just relying on signals
        self.number = self.generate_invoice_number()
    super().save(*args, **kwargs)
```

---

## Security Issues (MEDIUM SEVERITY)

### 16. **User Isolation Not Fully Checked in Views**
**File:** [invoices/views.py](invoices/views.py#L408)  
**Severity:** MEDIUM  
**Issue:** While `get_object_or_404(Invoice, pk=pk, user=request.user)` is used, some views query related objects without user check:
```python
invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
# Safe

available_credit = CreditNote.objects.get_client_credit_balance(invoice.client)
# If this manager method doesn't filter by user internally, could leak data!
```
**Problem:**
- CreditNote.objects won't filter by user unless explicitly done
- Accessing invoice.client.credit_notes could include other users' credits

**Suggested Fix:**
Always include user filter:
```python
available_credit = CreditNote.objects.filter(user=request.user, client=invoice.client).aggregate(...)
```

---

### 17. **Missing CSRF Protection on POST Endpoints**
**File:** [invoices/views.py](invoices/views.py#L13-70)  
**Severity:** MEDIUM  
**Issue:** While @login_required is present, some views have @require_POST without explicit CSRF token checking in AJAX:
```python
@login_required
@require_POST
def mark_anomaly_sorted(request, pk):
    # Good: Django middleware handles CSRF by default
    # BUT if using AJAX with HX-Request headers, verify token is sent
```
**Problem:**
- AJAX requests need explicit X-CSRFToken header
- If frontend doesn't send it, requests could be CSRF'd

**Suggested Fix:**
Verify in unit tests that all POST requests include CSRF token.

---

## Date/Timezone Issues (MEDIUM SEVERITY)

### 18. **timezone.now Used as Default Instead of Callable**
**File:** [invoices/models.py](invoices/models.py#L149-150)  
**Severity:** MEDIUM  
**Issue:** Using `timezone.now` as default value without callable:
```python
due_date = models.DateField()  # OK - no default
payment_date = models.DateField(default=timezone.now)  # WRONG!
issued_date = models.DateField(default=timezone.now)  # WRONG!
```
**Problem:**
- `timezone.now` is evaluated when the model Class is loaded, not when instance is created
- All records get the same date (when server started)
- Should use `default=timezone.now` (function) or `callable`

**Suggested Fix:**
```python
payment_date = models.DateField(default=date.today)  # For date, use date.today
issued_date = models.DateField(default=date.today)   # For date, use date.today
emailed_at = models.DateTimeField(default=timezone.now)  # For datetime, use timezone.now
```

---

## Missing Database Indexes (MEDIUM SEVERITY)

### 19. **Missing Index on Frequently Queried Fields**
**File:** [invoices/models.py](invoices/models.py)  
**Severity:** MEDIUM  
**Issue:** High-traffic fields lack indexes:
```python
class Invoice(TenantModel):
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    # No db_index=True! status is filtered 50+ times in queries
```
**Problem:**
- Queries like `.filter(status='PAID')` scan all rows without index
- Performance degrades as invoice count grows
- Dashboard queries could timeout

**Suggested Fix:**
```python
status = models.CharField(
    max_length=10, 
    choices=Status.choices, 
    default=Status.DRAFT,
    db_index=True  # Add this
)
is_quote = models.BooleanField(default=False, db_index=True)  # Add this
date_issued = models.DateField(default=date.today, db_index=True)  # Add this
```

---

## Minor Issues (LOW SEVERITY)

### 20. **Magic Strings in Status Checks**
**File:** Multiple files  
**Severity:** LOW  
**Issue:** Using literal strings instead of constants:
```python
if invoice.status == "DRAFT":  # Inconsistent
if invoice.status == Invoice.Status.DRAFT:  # Correct
```
**Problem:**
- Easy to typo ("DRAT" instead of "DRAFT")
- Refactoring status values breaks multiple places
- Some views use strings, some use constants

**Suggested Fix:**
Always use `Invoice.Status.DRAFT` enum values.

---

### 21. **Inconsistent Credit Application Logic**
**File:** [invoices/views.py](invoices/views.py#L929-960)  
**Severity:** LOW  
**Issue:** Credit notes are manually deleted after use instead of marking as used:
```python
if credit_note.balance <= 0:
    credit_note.delete()  # Deletes audit trail!
else:
    credit_note.save()
```
**Problem:**
- Deleting records breaks accounting audit trail
- No way to trace which credit was applied to which invoice
- Makes reconciliation impossible

**Suggested Fix:**
```python
# Keep records, just mark as inactive:
class CreditNote(TenantModel):
    is_active = models.BooleanField(default=True)

# Then in payment logic:
if credit_note.balance <= 0:
    credit_note.is_active = False
    credit_note.save()
else:
    credit_note.save()
```

---

## Recommendations Summary

### Priority 1 (Fix Immediately):
1. ✅ Fix Payment validation logic (Issue #2)
2. ✅ Fix Transaction handling in Invoice.save() (Issue #3)
3. ✅ Fix float() conversion for financial data (Issue #1)
4. ✅ Add proper UserProfile access guards (Issue #4)
5. ✅ Fix decimal zero comparison bug (Issue #9)

### Priority 2 (Fix This Sprint):
- Fix N+1 query in invoice_list
- Add division by zero guard in get_revenue_vs_target
- Fix quarterly revenue calculation
- Add form validation for overpayment credit notes
- Add database indexes on frequently queried fields
- Implement automatic status sync

### Priority 3 (Long-term Refactoring):
- Consolidate dashboard queries
- Implement comprehensive audit logging instead of deleting records
- Add test coverage for financial edge cases
- Document decimal handling best practices
- Create developer guide for avoiding financial calculation bugs

---

## Testing Recommendations

### Unit Tests Needed:
```python
# test_payment_validation.py
def test_new_payment_validation_excludes_self():
    """Ensure new payments don't double-count existing payments"""
    
def test_decimal_zero_comparison():
    """Test that 0% VAT is not replaced with default 15%"""
    
def test_user_profile_missing():
    """Test handling when profile doesn't exist"""
```

### Integration Tests:
- Full payment flow without exceeding invoice amount
- Invoice status sync from DRAFT when delivery logs exist
- Credit note application reduces balance correctly
- Quarterly revenue calculations match manual sums

---

## Performance Optimization Checklist

- [ ] Add `db_index=True` to: status, is_quote, date_issued, client_id
- [ ] Add `select_related()` for user.profile in dashboard view
- [ ] Convert Python loops to database aggregations in managers
- [ ] Cache UserProfile in request object
- [ ] Use `prefetch_related()` for delivery_logs in invoice_list

