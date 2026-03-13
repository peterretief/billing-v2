# Billing System Queuing Bug Fixes - Summary

## Overview
Fixed three critical bugs in the invoice queuing system that were causing:
1. Invoices marked as sent even though no email was sent
2. Invoices incorrectly flagged as sent with wrong status
3. Invoices being resent on nightly schedule when they should only send on day 1

---

## Bug #1: Status Marked PENDING Before Email Actually Sent ❌

### Location
**File**: `invoices/tasks.py` - Function `send_invoice_async()`

### Problem
```python
# BEFORE (WRONG):
with transaction.atomic():
    invoice.status = "PENDING"
    invoice.save()  # ← Status saved to database HERE
    
    # ... other operations ...
    
    if email_invoice_to_client(invoice):  # ← Email sent HERE
        return {"status": "success", ...}
    else:
        invoice.status = "DRAFT"  # ← Attempting to revert, but race condition
        invoice.save()
```

**Root Cause**: Status was set to PENDING and persisted to database BEFORE email_invoice_to_client() was called. If email failed and raised an exception instead of returning False, the status remained PENDING in the database even though no email was sent.

**Impact**: 
- Invoice shows PENDING status but was never emailed
- Client never receives invoice
- Status inconsistency with actual email delivery

### Solution
```python
# AFTER (FIXED):
with transaction.atomic():
    # Don't touch invoice status here
    # Status will be set by email_invoice_to_client only after successful send
    invoice.billed_items.all().update(is_billed=True)
    
    # Update last_billed_date for recurring items
    Item.objects.filter(...).update(last_billed_date=timezone.now().date())
    
    # Send the invoice - this will handle all status updates on success
    if email_invoice_to_client(invoice):
        logger.info(f"Invoice {invoice.id} sent successfully...")
        return {"status": "success", ...}
    else:
        logger.error(f"Failed to send invoice {invoice.id}")
        return {"status": "failed", ...}
```

**Fix Details**:
- Removed premature status update from `send_invoice_async()`
- Status is now set ONLY by `email_invoice_to_client()` after confirmed successful email send
- Invoice stays in DRAFT if email fails

---

## Bug #2: Redundant Status Updates in Multiple Places 🔄

### Location
Multiple files:
- `invoices/tasks.py` - `send_invoice_async()` (line 75)
- `items/services.py` - `import_recurring_to_invoices()` (line 162)
- `items/utils.py` - `email_item_invoice_to_client()` (line 103)

### Problem
Status and `is_emailed` flag were being set in THREE different places:

1. **In send_invoice_async()**: Set status BEFORE email send
2. **In import_recurring_to_invoices()**: Set status AFTER email send  
3. **In email_item_invoice_to_client()**: Set status AFTER sending

```python
# Three different places setting the same fields:
invoice.status = "PENDING"
invoice.is_emailed = True
invoice.emailed_at = now()
invoice.save()
```

**Root Cause**: Inconsistent flow with multiple status updates in different functions created:
- Race conditions
- Redundant database writes
- Possibility of inconsistent state if one update succeeds but another fails
- Code maintainability issues

### Solution
**Consolidated status updates**: Status is now set in ONLY ONE PLACE - inside the email functions AFTER confirmed successful send.

Before:
```
send_invoice_async():
  1. Set status to PENDING
  2. Call email_invoice_to_client()
  
import_recurring_to_invoices():
  1. Call email_item_invoice_to_client()
  2. Set status to PENDING
  
email_item_invoice_to_client():
  1. Send email
  2. Set status to PENDING
```

After:
```
send_invoice_async():
  1. Call email_invoice_to_client() → Handles status internally

import_recurring_to_invoices():
  1. Call email_item_invoice_to_client() → Handles status internally
  
email_item_invoice_to_client():
  1. Send email
  2. Create delivery log (confirms email success)
  3. Set status to PENDING ← ONLY place where status is updated
```

---

## Bug #3: Nightly Re-send of Day 1 Invoices 🌙

### Location
**File**: `items/services.py` - Function `import_recurring_to_invoices()`

### Problem
```python
# BEFORE (WRONG):
processed_invoices = []

for inv in new_invoices:
    try:
        if email_item_invoice_to_client(inv):  # ← Send email
            inv.status = "PENDING"
            inv.is_emailed = True
            inv.emailed_at = today
            inv.save()

            # IMPORTANT: Update the master template's date...
            templates.filter(client=inv.client).update(last_billed_date=today.date())
            # ↑ last_billed_date ONLY updated if email_item_invoice_to_client() returns True
            
            processed_invoices.append(inv)
        else:
            logger.error(f"Mail delivery failure for invoice {inv.id}")
    except Exception as e:
        logger.error(f"System error during dispatch...")
```

**Root Cause**: The `last_billed_date` was updated ONLY if the email send returned `True`. If email failed on Day 1:
- `last_billed_date` remained unchanged (still pointing to previous month)
- On Day 2 nightly schedule run, the item would be eligible for billing again
- The system would create and attempt to send the SAME invoice again

**Impact**:
- Same invoice sent multiple times to client
- Duplicate billing
- Client confusion with multiple copies of same invoice

### Solution
```python
# AFTER (FIXED):
processed_invoices = []

for inv in new_invoices:
    try:
        # FIX: Update last_billed_date BEFORE sending email
        # This ensures even if email fails, we don't retry sending the same invoice today
        templates.filter(client=inv.client).update(last_billed_date=today.date())
        
        # Send invoice - email_item_invoice_to_client handles all status updates on success
        if email_item_invoice_to_client(inv):
            logger.info(f"Successfully sent invoice {inv.id}...")
            processed_invoices.append(inv)
        else:
            logger.error(f"Mail delivery failure for invoice {inv.id}")
            # ↑ Even if email fails, last_billed_date is already updated above
    except Exception as e:
        logger.error(f"System error during dispatch...")
```

**Fix Details**:
- Moved `last_billed_date` update to BEFORE email send
- Now works correctly whether email succeeds or fails
- Prevents the daily schedule from creating duplicate invoices

**Flow After Fix**:
```
Day 1, 8:00 AM: process_daily_billing_queue runs
├─ Creates invoice
├─ Updates last_billed_date to Day 1 ✓
├─ Attempts to send email
│  ├─ Success: Invoice marked PENDING ✓
│  ├─ Email fails: Invoice stays DRAFT (but last_billed_date already updated)
└─ Result: No duplicate action possible

Day 1, 8:00 PM: process_daily_billing_queue runs (scheduled daily)
├─ Checks last_billed_date for this item
├─ Sees it's already today (from morning run)
├─ Excludes item from processing ✓
└─ Result: No duplicate invoice created
```

---

## Files Modified

### 1. `/opt/billing_v2/invoices/tasks.py`
**Function**: `send_invoice_async()`
**Changes**:
- Removed `invoice.status = "PENDING"` and `invoice.save()` (line 75)
- Removed email failure handling that tried to revert status
- Let `email_invoice_to_client()` handle status updates

### 2. `/opt/billing_v2/items/services.py`
**Function**: `import_recurring_to_invoices()`
**Changes in DISPATCH section**:
- Moved `templates.filter(client=inv.client).update(last_billed_date=today.date())` to BEFORE email send
- Removed redundant status update lines (status is now set only in `email_item_invoice_to_client()`)
- Removed `inv.status = "PENDING"`, `inv.is_emailed = True`, `inv.emailed_at = today` assignments

### 3. `/opt/billing_v2/items/utils.py`
**Function**: `email_item_invoice_to_client()`
**Changes**:
- Added clarifying comment about status update timing
- Confirmed this is the ONLY place where status should be updated for recurring invoices
- Status now only set after `InvoiceEmailStatusLog` is created (confirms email send success)

---

## Test Coverage

Created: `/opt/billing_v2/items/tests/test_queuing_system_bugs.py`

### Test Cases
1. **test_invoice_stays_draft_if_email_fails()**
   - Verifies invoice stays in DRAFT when email send fails
   - Confirms `is_emailed` remains False

2. **test_invoice_marked_pending_only_after_email_succeeds()**
   - Verifies invoice is marked PENDING only after successful email send
   - Checks that status update is not premature

3. **test_last_billed_date_updated_even_when_email_fails()**
   - Verifies `last_billed_date` is updated even if email fails
   - Prevents same invoice from being recreated on nightly run

4. **test_no_nightly_resend_after_successful_send()**
   - Full end-to-end test simulating nightly schedule runs
   - Confirms no duplicate invoices created on same day

---

## Impact Summary

| Bug | Severity | Impact | Fixed |
|-----|----------|--------|-------|
| Status marked before email | **Critical** | Invoice shows sent but wasn't | ✓ |
| Redundant status updates | **High** | Race conditions, inconsistent state | ✓ |
| Nightly re-sends | **Critical** | Duplicate invoices, billing errors | ✓ |

---

## Deployment Notes

### No Breaking Changes
- All changes are internal flow improvements
- No API changes
- No database migrations needed
- Existing invoices are unaffected

### Recommended Testing Before Production
1. Run test suite: `python manage.py test items.tests.test_queuing_system_bugs`
2. Manual test: Send invoice via `send_invoice_async` and verify status only changes after email succeeds
3. Monitor logs for next 24 hours to ensure no duplicate invoices

### Monitoring
After deployment, monitor:
- `BillingAuditLog` for duplicate entries
- `InvoiceEmailStatusLog` for delivery tracking
- Invoice status changes (should only change to PENDING after confirmed send)

---

## Related Issues Prevented
These fixes also prevent:
- Orphaned invoices (marked sent but no delivery log)
- Inconsistent reconciliation data
- Customer confusion with duplicate invoices
- Email audit trail corruption
