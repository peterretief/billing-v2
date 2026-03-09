# Reconciliation Payment Fix

## Problem

The reconciliation statement was showing payments that appeared to exceed invoice amounts. The issue was that the summary section and the transaction details were calculating payments differently:

- **Summary**: Only counted cash payments (`payment.amount`)
- **Transactions**: Showed cash + credit applied (`payment.amount + payment.credit_applied`)

This created an inconsistency where the balance appeared incorrect because credit applied was being counted in the transactions but not properly separated in the summary.

## Solution

### 1. Updated Reconciliation Calculation (`invoices/reconciliation.py`)

**Changed the summary calculation to:**
- Separate `payments_received` (cash only) from `credit_in_payments` (credit applied)
- Updated closing balance formula to account for both separately:
  ```
  closing_balance = opening_balance + invoices_sent - invoices_cancelled 
                    - payments_received - credit_in_payments - credit_notes_issued
  ```

### 2. Updated Reconciliation Template (`invoices/templates/invoices/client_reconciliation.html`)

**Now displays clearly:**
- **Payments Received (Cash)**: Only cash payments
- **Credit Applied to Invoices**: Credit used to pay invoices
- **Credit Notes Issued**: Separate line item

This makes it transparent that:
- If an invoice has a $1000 balance
- And a payment is made with $700 cash + $300 credit
- Then: Payments: -$700, Credit Applied: -$300, Closing: $0

### 3. Updated CSV Export (`invoices/recon_views.py`)

**CSV now shows:**
```
Opening Balance,       $0.00
Invoices Sent,         $1000.00
Payments Received (Cash),          -$700.00
Credit Applied to Invoices,        -$300.00
Credit Notes Issued,   $0.00
Closing Balance,       $0.00
```

### 4. Updated PDF Export (`invoices/recon_views.py`)

**PDF summary table now includes both:**
- Payments Received (Cash)
- Credit Applied to Invoices

### 5. Enhanced Payment Validation (`invoices/models.py`)

**Added validation to ensure:**
- Cash payment cannot exceed invoice balance
- Total payment (cash + credit) cannot exceed invoice balance
- Credit applied cannot be negative

```python
# Check that total payment (cash + credit) doesn't exceed balance
total_payment = self.amount + self.credit_applied
if total_payment > self.invoice.balance_due:
    raise ValidationError(
        f"Total payment (cash + credit: {currency} {total_payment}) cannot exceed "
        f"the balance due ({currency} {self.invoice.balance_due})"
    )
```

## How Payments with Credit Work

### Example: Paying a $1000 invoice with mixed cash and credit

**Before fix:**
```
Summary shows:
  Payments Received: $700
  
Transactions show:
  Payment: -$1000
  
Result: Confusing! Payments seem to exceed what was received
```

**After fix:**
```
Summary shows:
  Payments Received (Cash): $700
  Credit Applied to Invoices: $300
  
Transactions show:
  Payment: -$1000 (breakdown: $700 cash + $300 credit)
  
Result: Clear and consistent - total payment is $1000
```

## Testing

Run the new test suite:
```bash
python manage.py test invoices.tests.test_reconciliation_payments
```

This verifies:
- Payments cannot exceed invoice totals
- Reconciliation calculations are correct
- Cash and credit are properly separated
- Closing balances calculate correctly

## Affected Views

1. `/invoices/reconciliation/client/<id>/` - HTML reconciliation
2. `/invoices/reconciliation/client/<id>/csv/` - CSV export
3. `/invoices/reconciliation/client/<id>/pdf/` - PDF export

All now display the breakdown of cash vs. credit payments correctly.
