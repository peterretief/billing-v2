# Invoice Date Behavior - Creation vs Due Dates

## Scenario 1: Scheduled Invoice (1st of Month or Recurring Schedule)

When an invoice is **automatically generated** as part of a billing schedule (1st of month or recurring):

### Dates Assigned:
- **`date_issued`** = Date the task runs (TODAY)
- **`due_date`** = `date_issued` + client's `payment_terms` (default: 30 days)

### Example:
If the billing policy runs on March 1st and client has 30-day payment terms:
- `date_issued` = March 1, 2026
- `due_date` = March 31, 2026 (March 1 + 30 days)

### Code Location:
[items/services.py](items/services.py#L85-L95) - `import_recurring_to_invoices()` function

```python
days_to_due = getattr(client_obj, "payment_terms", 30) or 30
calculated_due_date = today.date() + timedelta(days=days_to_due)

invoice = Invoice.objects.create(
    user=user, 
    client=client_obj, 
    date_issued=today.date(),      # When task runs
    due_date=calculated_due_date,   # + Client payment terms
    status="DRAFT"
)
```

---

## Scenario 2: Manual Invoice Creation (Including Past Dates)

When you **create an invoice manually** through the form:

### Default Behavior:
When creating a NEW invoice, the form initializes with:
- **`date_issued`** = TODAY (current date)
- **`due_date`** = TODAY (current date)

### Manual Override:
Both fields are **fully editable**, so you can:
1. Set `date_issued` to any date in the past (balance books)
2. Set `due_date` independently to any date

### Code Location:
[invoices/forms.py](invoices/forms.py#L42-L70) - `InvoiceForm` class

```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    if not self.instance.pk:
        today = timezone.now().date()
        self.fields["date_issued"].initial = today      # Default today
        self.fields["due_date"].initial = today         # Default today
    self.fields["number"].required = False
```

### For Past Invoice:
To create an invoice in the past to balance books:
- Set `date_issued` to the past date (e.g., Feb 15, 2026)
- Set `due_date` to whenever it was due (e.g., Mar 15, 2026)
- Status: Usually DRAFT initially, then manually change to SENT/PAID as needed

---

## Key Differences

| Aspect | Scheduled Invoice | Manual Creation |
|--------|-------------------|-----------------|
| `date_issued` | TODAY (execution date) | TODAY (form default, editable) |
| `due_date` | TODAY + payment_terms | TODAY (form default, editable) |
| Purpose | Recurring billing | Manual adjustments, back-dating |
| Payment Terms Used | Applied automatically | Not applied (manual entry) |
| Status | Created as DRAFT | Created as DRAFT (form default) |

---

## Related Models

**Client Model:**
- `payment_terms` field (default 14 days) - number of days until invoice is due

**Invoice Model:**
- `date_issued` - when invoice was created (always stored, used for reporting)
- `due_date` - payment deadline
- `status` - DRAFT, PENDING, PAID, OVERDUE, CANCELLED
- `created_at` - system timestamp (auto-set when record created)

---

## Email Scheduling Note

**There is no explicit "email scheduling" feature.** When you send an invoice:
- The invoice is sent immediately via email (or scheduled async task)
- Email task assignment creates an `InvoiceEmailStatusLog` entry
- Future work could add delayed send capability, but currently unavailable

