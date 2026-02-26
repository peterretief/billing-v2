# Invoice Reporting Consistency Guide

## Overview

This document outlines the system for consistent invoice reporting across the entire billing application. The system ensures that quotes, draft invoices, and cancelled invoices are handled consistently across:

- Dashboard totals
- Client statements
- Reconciliation reports  
- CSV exports
- Manager methods and querysets
- Tax calculations

## Filtering Rules

All invoice reporting must follow these rules:

### Rule 1: DRAFT Invoices - NEVER Include
- **Status**: All statuses
- **Where**: Never included in any financial totals
- **Rationale**: Drafts are incomplete and not sent to clients
- **Implementation**: `.exclude(status="DRAFT")`

### Rule 2: QUOTES - NEVER Include in Financial Totals
- **is_quote**: Boolean field that identifies quotes
- **Where**: Visible in transaction history but excluded from all financial calculations
- **Rationale**: Quotes are proposals, not invoices. Converting to invoice is a separate action
- **Implementation**: `.exclude(is_quote=True)` in all aggregation methods

### Rule 3: CANCELLED Invoices - Show History, Exclude from Totals
- **Status**: CANCELLED
- **Where**: Included in transaction lists but excluded from financial totals
- **Rationale**: Cancelled invoices were sent but then revoked. They affect transaction history but not current position
- **Implementation**: `.exclude(status="CANCELLED")` in aggregation, but shown in all transaction lists

### Rule 4: PENDING/OVERDUE/PAID - ALWAYS Include
- **Status**: PENDING, OVERDUE, PAID
- **Where**: Included in all financial calculations (unless also a quote)
- **Rationale**: These represent actual issued invoices

## Implementation Details

### Updated Components

#### 1. Invoice Manager Methods (`invoices/managers.py`)

✅ `active()` - Returns non-draft, non-cancelled, non-paid, non-quote invoices
```
.exclude(status__in=["DRAFT", "CANCELLED", "PAID"], is_quote=True)
```

✅ `totals()` - Returns financial totals (billed and paid, excluding quotes)
```
.exclude(is_quote=True).aggregate(billed=Sum(...), paid=Sum(...))
```

✅ `get_tax_summary()` - Tax collected only from actual invoices, not quotes
```
.filter(..., is_quote=False)
```

✅ `get_tax_year_report()` - Annual revenue excluding quotes
```
.filter(..., is_quote=False)
```

#### 2. Dashboard View (`invoices/views.py`)

✅ Dashboard displays:
- **Total Billed**: Active invoices (excludes quotes, cancelled, drafts)
- **Total Quotes**: Tracked separately (includes drafted quotes)
- **Outstanding**: Unpaid invoices (excludes quotes)

#### 3. Client Statements (`clients/views.py`, `clients/templates/clients/client_statement.html`)

✅ Statement totals exclude quotes and cancelled invoices
✅ Transaction list shows all documents (invoices, quotes, cancelled) with visual marking

#### 4. CSV Export (`clients/views.py::client_statement_csv()`)

✅ Summary section excludes quotes and cancelled invoices
✅ Transaction detail list shows all documents

#### 5. Reconciliation (`invoices/reconciliation.py`)

✅ Opening/closing balances exclude quotes
✅ Transaction summary excludes quotes
✅ All calculations use ` is_quote=False` filter

#### 6. Templates

✅ [clients/templates/clients/client_detail.html](clients/templates/clients/client_detail.html)
- Type column shows INVOICE vs QUOTE
- Cancelled rows show strikethrough + gray text
- Quote rows highlighted in yellow

✅ [clients/templates/clients/client_statement.html](clients/templates/clients/client_statement.html)
- Type column distinguishes invoices from quotes
- Cancelled invoices marked with strikethrough
- Totals shown separately from transaction history

## Testing & Audit

### Test Suite

Run the comprehensive test suite:
```bash
python manage.py test invoices.tests.test_invoice_reporting_consistency
```

This test suite verifies:
- ✓ Draft invoices excluded from all totals
- ✓ Quotes excluded from financial totals
- ✓ Cancelled invoices excluded from totals but visible in history
- ✓ Paid invoices included in totals
- ✓ Manager methods consistency
- ✓ No double-counting of payments
- ✓ Audit trail consistency (double-entry verification)

### Runtime Audit System

Verify consistency in production:

```bash
# Audit a specific user
python manage.py audit_invoices --user <username>

# Audit all users
python manage.py audit_invoices --all

# Output as JSON
python manage.py audit_invoices --all --json
```

The audit system (`invoices/audit.py`) verifies:

1. **Billed Invoices**: All methods report same total
2. **Outstanding Invoices**: Manager vs direct calculation match
3. **Quote Exclusion**: Quotes never in financial totals
4. **Cancelled Exclusion**: Cancelled invoices excluded properly
5. **Draft Exclusion**: Drafts never included

## Visual Indicators

Users can distinguish different invoice types:

| Type | Visual Indicator | Financial Impact |
|------|------------------|------------------|
| Invoice - PENDING | Normal | Included in totals |
| Invoice - PAID | Normal | Included in billed |
| Invoice - CANCELLED | ~~Strikethrough~~ Gray | Excluded from totals |
| Quote - PENDING | Yellow background + "QUOTE" badge | Excluded from totals |
| Quote - CANCELLED | ~~Strikethrough~~ Gray + Yellow | Excluded from totals |
| Invoice - DRAFT | (not shown in lists) | Excluded from totals |

## Common Pitfalls to Avoid

❌ **Don't**:
```python
# Including quotes in invoice totals
Invoice.objects.filter(user=user).aggregate(Sum("total_amount"))

# Aggregating without excluding drafts
invoices.aggregate(Sum("total_amount"))

# Assuming active() excludes quotes (it doesn't)
# → Use active().exclude(is_quote=True)
```

✅ **Do**:
```python
# Use manager methods that handle rules
Invoice.objects.filter(user=user).totals()["billed"]

# Use manager shortcuts
Invoice.objects.get_total_outstanding(user)
Invoice.objects.get_dashboard_stats(user)

# Or explicitly in views
Invoice.objects.filter(user=user).exclude(
    status__in=["DRAFT", "CANCELLED"], 
    is_quote=True
).aggregate(total=Sum("total_amount"))
```

## Future Enhancements

Potential improvements:
1. **Webhook/event-based audit triggers**: Audit changes when invoices are created/modified
2. **Materialized views**: Cache totals for performance
3. **Audit history**: Track when/why rules were applied
4. **Multi-currency reconciliation**: Enhanced consistency checking
5. **Machine-readable audit reports**: Standard format for compliance

## References

- [Manager Implementation](invoices/managers.py)
- [Audit Utility](invoices/audit.py)
- [Test Suite](invoices/tests/test_invoice_reporting_consistency.py)
- [Management Command](invoices/management/commands/audit_invoices.py)
- [Dashboard View](invoices/views.py#L204-L250)
- [Client Statement](clients/views.py#L92-L165)
