# Reconciliation System - Quick Reference

## Quick Links

| What | Where |
|------|-------|
| View all clients recon | `/invoices/reconciliation/` |
| View client recon | `/invoices/reconciliation/client/<id>/` |
| Export clients CSV | `/invoices/reconciliation/export-csv/` |
| Export client CSV | `/invoices/reconciliation/client/<id>/csv/` |
| Export client PDF | `/invoices/reconciliation/client/<id>/pdf/` |
| Manage credit notes | Django Admin → Invoices → Credit Notes |

---

## CreditNote Model

### Create in Admin
```python
CreditNote.objects.create(
    user=request.user,
    client=client,
    invoice=related_invoice,  # Optional
    note_type='ADJUSTMENT',   # or OVERPAYMENT, CANCELLATION, OTHER
    amount=Decimal('100.00'),
    reference='CN2026-001',
    description='Early payment discount',
    issued_date=date.today()
)
```

### Query Examples
```python
# All credits for client
CreditNote.objects.filter(user=user, client=client)

# Available credits only
CreditNote.objects.filter(user=user, client=client).filter(balance__gt=0)

# By type
CreditNote.objects.filter(user=user, note_type='OVERPAYMENT')

# By date range
CreditNote.objects.filter(user=user, issued_date__range=[start, end])
```

---

## Utilities Usage

### Single Client Reconciliation
```python
from invoices.reconciliation import ClientReconciliation
from datetime import date

recon = ClientReconciliation(
    client=client_obj,
    user=request.user,
    start_date=date(2026, 1, 1),
    end_date=date(2026, 2, 28)
)

# Get various data
summary = recon.get_summary()          # Summary stats
transactions = recon.get_transactions() # Full trans list
cancelled = recon.get_cancelled_invoices_sent()
credit = recon.get_outstanding_credit()
report = recon.get_full_report()        # Everything
```

### All Clients Reconciliation
```python
from invoices.reconciliation import AllClientsReconciliation
from datetime import date

all_recon = AllClientsReconciliation(
    user=request.user,
    end_date=date(2026, 2, 28)
)

summaries = all_recon.get_all_clients_summary()
# [
#   {
#     'client': Client,
#     'outstanding_balance': Decimal,
#     'total_payments': Decimal,
#     'credit_balance': Decimal,
#     'cancelled_sent_count': int,
#     'net_position': Decimal,
#   },
#   ...
# ]
```

---

## Summary Structure

```python
summary = {
    'opening_balance': Decimal('1000.00'),
    'invoices_sent': Decimal('500.00'),
    'invoices_cancelled': Decimal('200.00'),
    'payments_received': Decimal('300.00'),
    'credit_notes_issued': Decimal('100.00'),
    'closing_balance': Decimal('900.00'),
    'transaction_count': 12,
}
```

---

## Transaction Structure

```python
transaction = {
    'type': 'INVOICE',              # INVOICE, PAYMENT, CREDIT_NOTE, INVOICE_CANCELLED
    'date': date(2026, 1, 15),
    'description': 'Invoice INV-001',
    'amount': Decimal('500.00'),    # Positive for debits, negative for credits
    'running_balance': Decimal('1500.00'),
    'invoice': Invoice,             # For INVOICE types
    'payment': Payment,             # For PAYMENT types
    'credit_note': CreditNote,      # For CREDIT_NOTE types
    'detail': 'Due: 2026-02-15'     # Additional info
}
```

---

## Views & Templates

### View Arguments
```python
# client_reconciliation_statement
name='invoices:client_reconciliation'
args=[client_id]
kwargs={'start_date': '2026-01-01', 'end_date': '2026-02-28'}

# all_clients_reconciliation  
name='invoices:all_clients_reconciliation'
kwargs={'end_date': '2026-02-28'}
```

### Context Variables
```python
# Client recon context
context = {
    'client': Client,
    'report': {
        'client': Client,
        'period_start': date,
        'period_end': date,
        'summary': dict,
        'transactions': list,
        'cancelled_sent': QuerySet,
        'outstanding_credit': Decimal,
    },
    'currency': 'USD',
    'start_date': date,
    'end_date': date,
}

# All clients context
context = {
    'summaries': list,          # Of summary dicts
    'end_date': date,
    'currency': 'USD',
    'totals': {
        'outstanding': Decimal,
        'payments': Decimal,
        'credits': Decimal,
        'client_count': int,
    }
}
```

---

## Common Code Patterns

### Check if client has credit
```python
from invoices.models import CreditNote

balance = CreditNote.objects.filter(
    user=user, 
    client=client
).aggregate(
    total=Sum('balance')
)['total'] or Decimal('0.00')

if balance > 0:
    print(f"Client has ${balance} available credit")
```

### Get client position
```python
from invoices.models import Invoice
from django.db.models import Sum

active_invoices = Invoice.objects.filter(
    user=user,
    client=client,
    status__in=['PENDING', 'OVERDUE']
).aggregate(
    total=Sum('total_amount')
)['total'] or Decimal('0.00')

payments = Invoice.objects.filter(
    user=user,
    client=client
).aggregate(
    paid=Sum('payments__amount')
)['paid'] or Decimal('0.00')

balance_due = active_invoices - payments
```

### Create credit for overpayment
```python
# Assuming payment exceeds invoice
overage = payment_amount - invoice.balance_due

CreditNote.objects.create(
    user=user,
    client=invoice.client,
    invoice=invoice,
    note_type='OVERPAYMENT',
    amount=overage,
    reference=f"CN{date.today().strftime('%Y%m%d')}",
    description=f"Overpayment on invoice {invoice.number}",
    issued_date=date.today()
)
```

### Generate all clients CSV
```python
from invoices.recon_views import all_clients_reconciliation_csv, AllClientsReconciliation
from datetime import date

# Get data
recon = AllClientsReconciliation(user, date.today())
summaries = recon.get_all_clients_summary()

# Create response
response = HttpResponse(content_type='text/csv')
writer = csv.writer(response)

# Write headers
writer.writerow(['Client', 'Outstanding', 'Payments', 'Credit', 'Net'])

# Write data
for s in summaries:
    writer.writerow([
        s['client'].name,
        s['outstanding_balance'],
        s['total_payments'],
        s['credit_balance'],
        s['net_position'],
    ])

return response
```

---

## Configuration

### Optional: Enable PDF Export
Install reportlab:
```bash
pip install reportlab
```

Check in recon_views.py:
```python
REPORTLAB_AVAILABLE = True  # Auto-detected
```

### Date Filters
Client statement:
- `?start_date=2026-01-01&end_date=2026-02-28`
- Both optional, ISO format (YYYY-MM-DD)

All clients:
- `?end_date=2026-02-28`
- Optional, ISO format

### URL Parameters
```
GET /invoices/reconciliation/client/123/
GET /invoices/reconciliation/client/123/?start_date=2026-01-01&end_date=2026-02-28
GET /invoices/reconciliation/client/123/csv?start_date=2026-01-01&end_date=2026-02-28
GET /invoices/reconciliation/client/123/pdf?end_date=2026-02-28
GET /invoices/reconciliation/?end_date=2026-02-28
GET /invoices/reconciliation/export-csv/?end_date=2026-02-28
```

---

## Testing Examples

### Test Credit Note Creation
```python
from invoices.models import CreditNote
from decimal import Decimal
from datetime import date

cn = CreditNote.objects.create(
    user=user,
    client=client,
    note_type='ADJUSTMENT',
    amount=Decimal('50.00'),
    description='Test credit',
)

assert cn.balance == Decimal('50.00')  # Auto-set
assert cn.balance == cn.amount
```

### Test Client Reconciliation
```python
from invoices.reconciliation import ClientReconciliation

recon = ClientReconciliation(client, user)
report = recon.get_full_report()

assert 'summary' in report
assert 'transactions' in report
assert 'cancelled_sent' in report
assert 'outstanding_credit' in report
```

### Test Calculations
```python
from datetime import date

recon = ClientReconciliation(client, user, date(2026, 1, 1), date(2026, 1, 31))
summary = recon.get_summary()

# Verify math
expected_closing = (
    summary['opening_balance'] +
    summary['invoices_sent'] -
    summary['invoices_cancelled'] -
    summary['payments_received'] -
    summary['credit_notes_issued']
)

assert expected_closing == summary['closing_balance']
```

---

## Troubleshooting

### "Closing balance doesn't match"
- Check date range is correct
- Exclude DRAFT invoices
- Verify cancelled reversals included
- Review credit notes summary

### "Missing transactions"
- Ensure invoices have correct status
- Check payment date ranges
- Verify credit notes issued_date
- Ensure is_emailed=True for cancelled

### "Performance slow"
- Review query count (use django-debug-toolbar)
- Consider date range limits
- Check for missing database indexes
- Cache all-clients for heavy users

### "PDF export fails"
- Verify reportlab installed: `pip install reportlab`
- Check error log for specific issue
- Fallback to CSV export

---

## Key Table for Reconciliation Logic

| Status | Included in Outstanding | Included in Recon |
|--------|-------------------------|-------------------|
| DRAFT | ❌ No | ❌ No |
| PENDING | ✅ Yes | ✅ Yes |
| PAID | ❌ No | ✅ Yes |
| OVERDUE | ✅ Yes | ✅ Yes |
| CANCELLED (not sent) | ❌ No | ❌ No |
| CANCELLED (sent) | ❌ No | ✅ Yes (as reversal) |

---

## Quick Deployment

1. **Pull changes**: Latest code includes new files
2. **Migrate database**: `python manage.py migrate invoices`
3. **Verify**: `python manage.py check` (should be 0 silenced)
4. **Test URLs**: Access `/invoices/reconciliation/`
5. **Create credit note**: Admin → Invoices → Credit Notes
6. **Export options**: HTML/CSV/PDF all work

---

## Monitoring Checklist

After deployment:
- [ ] Reconciliation statements loading
- [ ] Calculations correct (spot check)
- [ ] CSV exports open in Excel
- [ ] PDF exports work (if reportlab)
- [ ] Credit notes appear in admin
- [ ] No N+1 query issues
- [ ] Date filters working
- [ ] Multi-tenant isolation working

---

For full documentation, see:
- `RECONCILIATION_GUIDE.md` - User guide
- `RECONCILIATION_IMPLEMENTATION.md` - Technical details
