# Invoice Cancellation and Payment Rules

## Overview

This document describes the business rules that prevent payment-related data corruption when managing invoices and payments.

## The Rules

### Rule 1: PAID invoices → CANCELLED auto-creates credit note

**When:** An invoice with status `PAID` is cancelled (status changed to `CANCELLED`)

**What happens:**
1. Invoice status changes to `CANCELLED`
2. System automatically creates a `CreditNote` for the full paid amount
3. Credit note type is `CANCELLATION`
4. Credit note is linked to the cancelled invoice
5. Credit note can be applied to future invoices

**Why:** When a paid invoice is cancelled, the money paid should be converted to a credit for the client, not lost.

**Example:**
```
Invoice ABC-123: $1,000 (PAID)
Payment received: $1,000

User cancels invoice:
→ Invoice ABC-123 becomes CANCELLED
→ CreditNote CN-ABC-123 created for $1,000
→ Client can use $1,000 credit on future invoices
```

### Rule 2: Payments never exceed invoice amount

**Applies to:** All payment operations

**Validation checks (in order):**

1. **No payments on DRAFT invoices**
   - User: Cannot add a payment to a Draft invoice
   - Fix: Send invoice first (change to PENDING status)

2. **No payments on CANCELLED invoices**
   - User: Cannot add a payment to a Cancelled invoice
   - Fix: System prevents this at validation level

3. **Total payments cannot exceed invoice amount**
   - Core rule: `Sum of all payments (cash + credit) ≤ Invoice total amount`
   - User: You cannot create a payment that would cause total paid to exceed the invoice
   - Fix: Reduce payment amount or check if credits are being double-applied

4. **Individual cash payment must not exceed balance due**
   - Rule: `Cash payment ≤ (Invoice total - Already paid)`
   - User: You cannot overpay with cash
   - Fix: Reduce cash payment amount

5. **No negative payments or credits**
   - Validations: amount ≥ 0, credit_applied ≥ 0
   - User: Cannot enter negative amounts
   - Fix: Enter positive amounts only

**Why:** These rules prevent:
- Applying phantom payments to unsent invoices
- Paying more than what was invoiced
- Data corruption from concurrent payments
- Accidental negative amounts

## Prevention Logic

### In Payment.clean()

```python
# RULE 1: Check invoice status
if self.invoice.status == "DRAFT":
    raise ValidationError("Cannot add payment to Draft invoice")

if self.invoice.status == "CANCELLED":
    raise ValidationError("Cannot add payment to Cancelled invoice")

# RULE 2: Calculate if total paid would exceed invoice amount
existing_paid = sum of all other payments on this invoice
total_would_be = existing_paid + this_payment
if total_would_be > invoice.total_amount:
    raise ValidationError("Would exceed invoice amount")

# RULE 3: Individual cash payment must not exceed balance
if self.amount > invoice.balance_due:
    raise ValidationError("Cash payment exceeds balance due")

# RULE 4 & 5: No negative amounts
if self.amount < 0 or self.credit_applied < 0:
    raise ValidationError("Amounts must be positive")
```

### In Invoice.clean()

```python
# Validate PAID→CANCELLED transitions
if original.status == PAID and new.status == CANCELLED:
    # Ensure no data corruption
    if total_paid > total_amount:
        raise ValidationError("Payment exceeds amount - data corruption!")
```

### In Invoice.save()

```python
# Auto-create credit when PAID→CANCELLED
if status changed from PAID to CANCELLED:
    CreditNote.create(
        type=CANCELLATION,
        amount=total_paid,
        linked_to_invoice=self
    )
```

## Testing the Rules

### Test 1: Normal cancellation (no payment)
```python
invoice = create_draft_invoice($1000)
invoice.status = CANCELLED
invoice.save()  # ✓ Succeeds - no credit note (no payment to credit)
```

### Test 2: Paid invoice cancellation (creates credit)
```python
invoice = create_paid_invoice($1000)
payment = Payment.create($1000)
invoice.status = CANCELLED
invoice.save()  # ✓ Succeeds
# → CreditNote CN-INV-001 created for $1000
```

### Test 3: Prevent overpayment
```python
invoice = create_invoice($100)

# Try to create $150 payment
payment = Payment($150)
payment.full_clean()  # ✗ Raises ValidationError: exceeds balance due

# Correct: $100 payment
payment = Payment($100)
payment.full_clean()  # ✓ Passes
```

### Test 4: Prevent duplicate payments
```python
invoice = create_invoice($100)

payment1 = Payment($60)
payment1.save()  # ✓ Succeeds

payment2 = Payment($50)
payment2.save()  # ✓ Succeeds (total $110 > $100)
# ✗ Actually fails - total_would_be ($110) > invoice.total ($100)
```

### Test 5: Prevent payment on CANCELLED
```python
invoice = create_invoice($100, status=CANCELLED)

payment = Payment($50)
payment.full_clean()  # ✗ Raises: Cannot pay cancelled invoice
```

## Error Messages

### For Users

**"Cannot add a payment to a Draft invoice."**
- Status: DRAFT
- Fix: Send the invoice first (change status to PENDING)

**"Cannot add a payment to a Cancelled invoice."**
- Status: CANCELLED
- Fix: Uncancel the invoice if needed (if payment was made due to error)

**"Payment would cause total paid (R 1,150.00) to exceed invoice amount (R 1,000.00). Current total paid: R 600.00, this payment: R 550.00"**
- Issue: Creating this payment would overpay
- Fix: Reduce payment to max R 400.00 (R 1,000 - R 600)

**"Cash payment amount (R 200) cannot exceed the balance due (R 150)"**
- Issue: Invoice has balance due of R 150, trying to pay R 200
- Fix: Only pay R 150

**"Cannot cancel invoice: Payment (R 1,150) exceeds invoice amount (R 1,000). This is a data integrity error."**
- Issue: Data corruption detected
- Fix: This shouldn't happen - indicates a bug in system. Report to support.

## Database Impact

### Tables Modified

- `invoices_invoice` - Added automatic credit creation logic in `save()`
- `invoices_payment` - Enhanced validation in `clean()`
- `invoices_creditnote` - New records created automatically for cancellations

### Record Creation Flow

```
User cancels PAID invoice ABC-123:
  1. Invoice record: status PAID → CANCELLED
  2. Auto-create CreditNote record (type=CANCELLATION)
  3. CreditNote.amount = Invoice.total_paid
  4. CreditNote.reference = "CN-ABC-123"
  5. CreditNote.invoice_id = ABC-123 (linkage)
  6. CreditNote.description = "Credit from cancelled invoice ABC-123"
```

## FAQ

### Q: What if an invoice was paid, then accidentally cancelled?
**A:** A credit note will be created automatically. You can:
1. Un-cancel the invoice (change status back to PAID)
2. Delete the auto-created credit note if needed
3. Or keep both and use the credit on another invoice

### Q: What if I need to refund a client instead of giving them a credit note?
**A:** You would typically:
1. Create a manual negative payment entry (if system allows)
2. Or create an offsetting invoice for the refund amount
3. Current system assumes credits are preferred to cash refunds

### Q: Can I apply a credit from one invoice's cancellation to a different client's invoice?
**A:** No, credit notes are tied to specific clients. You can only apply the credit to invoices for that same client.

### Q: What if an invoice is OVERDUE and gets paid, then cancelled - does it still create a credit?
**A:** Yes. The rule is: if status is PAID and you cancel it, a credit is created. The prior status (whether PENDING or OVERDUE) before PAID doesn't matter.

### Q: Can I prevent a paid invoice from being cancelled?
**A:** Not directly through the rule system. However, you could:
1. Remove permissions for users to cancel paid invoices
2. Add business logic to require manager approval for cancelling paid invoices
3. Or implement an audit hook that logs all cancellations

## Implementation Details

### Files Modified

- `/opt/billing_v2/invoices/models.py`
  - `Invoice.clean()` - Added validation for PAID→CANCELLED
  - `Invoice.save()` - Added auto-credit creation logic
  - `Payment.clean()` - Enhanced with 5-rule validation

### Imports Required

```python
from django.core.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal
```

### Transaction Safety

Auto-credit creation is wrapped in `transaction.atomic()` to ensure:
- Either both invoice update AND credit creation succeed
- Or both rollback (no partial updates)

## Monitoring and Alerts

### What to Monitor

1. **Credit notes created via auto-cancellation**
   - Count and amount per client
   - Should match cancelled payments

2. **Validation errors in payments**
   - "Payment would cause total paid to exceed" errors
   - Indicates users hitting overpayment limits

3. **Data corruption alerts**
   - "Payment exceeds amount - data corruption" errors
   - Indicates a bug if this ever appears

### Queries for Monitoring

```sql
-- Credit notes created from cancellations
SELECT * FROM invoices_creditnote 
WHERE note_type = 'CANCELLATION' 
ORDER BY created_at DESC;

-- Cancelled invoices with their auto-created credits
SELECT i.number, i.total_amount, i.total_paid, cn.amount
FROM invoices_invoice i
LEFT JOIN invoices_creditnote cn ON cn.invoice_id = i.id
WHERE i.status = 'CANCELLED' AND cn.note_type = 'CANCELLATION'
ORDER BY i.date_issued DESC;

-- Recent payment validation errors (check logs)
SELECT * FROM payment_validation_errors WHERE created_at > NOW() - INTERVAL 7 DAY;
```

## Version History

**v1.0** (February 25, 2026)
- Initial implementation of cancellation credit rules
- Payment overpayment prevention (5 validation rules)
- Auto-credit creation for PAID→CANCELLED transitions
