# Manager Methods Documentation

This document provides a comprehensive overview of all manager methods, their purposes, parameters, return values, and call graphs showing what calls each method.

---

## ItemManager (items/managers.py)

### `can_be_invoiced(item_ids)`

**Purpose:** Validates whether selected items are eligible to be invoiced (business rule: can only invoice unprocessed items).

**Parameters:**
- `item_ids` (list): List of Item IDs to validate

**Returns:**
- tuple: `(can_invoice: bool, count_already_invoiced: int)`
  - `can_invoice`: True if ALL items are unprocessed (invoice_id is NULL)
  - `count_already_invoiced`: Number of items already linked to invoices

**Call Graph:**
```
items/views.py: CreateInvoiceFromItemsView.post() [line 119]
    → Item.objects.can_be_invoiced(selected_ids)
    → Used to prevent double-invoicing of items
```

**Related:** Similar method exists in TimesheetManager for timesheet entries.

---

### `get_unprocessed(user, client=None)`

**Purpose:** Retrieves all unprocessed items for a user (items not yet linked to any invoice).

**Parameters:**
- `user` (User): The user who owns the items
- `client` (Client, optional): If provided, filters to only this client's items

**Returns:**
- QuerySet of Item objects where invoice_id is NULL

**Call Graph:**
```
clients/summary.py: ClientSummary.get_items() [approx line 110]
    → Item.objects.get_unprocessed(user, client)
    → Returns queryset for processing calculations
    → Used to display unprocessed item counts on client detail pages
```

**Data Flow:**
- Used in `get_unprocessed_value()` for total value calculations
- Feeds into progress bar displays on client summary pages

---

### `get_unprocessed_value(user, client=None)`

**Purpose:** Calculates the total monetary value of unprocessed items (sum of quantity × unit_price).

**Parameters:**
- `user` (User): The user who owns the items
- `client` (Client, optional): If provided, limits calculation to this client

**Returns:**
- Decimal: Total value in currency (0 if no unprocessed items)

**Call Graph:**
```
clients/summary.py: ClientSummary.get_items() [approx line 115]
    → Item.objects.get_unprocessed_value(user, client)
    → Returns total value for progress bar percentage calculation

clients_summary_dashboard.html:
    → AllClientsSummary.get_totals() aggregates all clients' unprocessed values
    → Displays in "Items Processing Status" card
    → Shows value-based progress (e.g., "R100/R200 Processed")
```

**Calculation:** `Sum(quantity × unit_price)` for all unprocessed items

---

## TimesheetManager (timesheets/managers.py)

### `can_be_invoiced(entry_ids)`

**Purpose:** Validates whether selected timesheet entries are eligible to be invoiced (business rule: can only invoice unprocessed entries).

**Parameters:**
- `entry_ids` (list): List of TimesheetEntry IDs to validate

**Returns:**
- tuple: `(can_invoice: bool, count_already_invoiced: int)`

**Call Graph:**
```
timesheets/views.py: CreateInvoiceFromTimesheetsView.post() [line 391]
    → TimesheetEntry.objects.can_be_invoiced(selected_ids)
    → Used to prevent double-invoicing of timesheet entries
```

**Related:** Parallel to ItemManager.can_be_invoiced()

---

### `get_unprocessed(user, client=None)`

**Purpose:** Retrieves all unprocessed timesheet entries for a user (entries not yet linked to any invoice).

**Parameters:**
- `user` (User): The user who owns the timesheet entries
- `client` (Client, optional): If provided, filters to only this client's entries

**Returns:**
- QuerySet of TimesheetEntry objects where invoice_id is NULL

**Call Graph:**
```
clients/summary.py: ClientSummary.get_timesheets() [approx line 65]
    → TimesheetEntry.objects.get_unprocessed(user, client)
    → Returns queryset for processing calculations
    → Used to display unprocessed timesheet counts on client detail pages
```

---

### `get_unprocessed_value(user, client=None)`

**Purpose:** Calculates the total monetary value of unprocessed timesheet entries (sum of hours × hourly_rate).

**Parameters:**
- `user` (User): The user who owns the timesheet entries
- `client` (Client, optional): If provided, limits calculation to this client

**Returns:**
- Decimal: Total value in currency (0 if no unprocessed entries)

**Call Graph:**
```
clients/summary.py: ClientSummary.get_timesheets() [approx line 70]
    → TimesheetEntry.objects.get_unprocessed_value(user, client)
    → Returns total value for progress bar percentage calculation

clients_summary_dashboard.html:
    → AllClientsSummary.get_totals() aggregates all clients' unprocessed timesheet values
    → Displays in "Timesheets Processing Status" card
    → Shows value-based progress (e.g., "R500/R800 Processed")
```

**Calculation:** `Sum(hours × hourly_rate)` for all unprocessed entries

---

## InvoiceQuerySet (invoices/managers.py)

### `with_totals()`

**Purpose:** Annotates queryset with aggregated payment totals for each invoice using a Subquery.

**Returns:**
- QuerySet with additional 'annotated_paid' field containing total payments

**Key Pattern:** Uses Subquery to safely aggregate related Payment objects, handling cases where no payments exist (returns 0.00).

**Call Graph:**
```
InvoiceManager methods that need payment information:
    → .with_totals() 
    → get_total_outstanding()
    → get_dashboard_stats()
    → get_tax_summary()
    → get_user_stats()
    → get_client_stats()
    → get_client_outstanding()
    → etc.

All places calculating outstanding balances (paid vs total_amount):
    → balance = total_amount - annotated_paid
```

---

### `active()`

**Purpose:** Filters to "active" invoices (those representing outstanding balance).

**Exclusions:** DRAFT, CANCELLED, PAID statuses and all Quotes

**Call Graph:**
```
InvoiceManager.get_total_outstanding(user) [approx line 185]
    → .filter(user=user).active().totals()
    → Used by dashboard outstanding calculation
```

**Business Context:** DRAFT invoices haven't been sent, CANCELLED/PAID are settled, so they don't represent money owed.

---

### `totals()`

**Purpose:** Aggregates total billed and total paid amounts for the queryset.

**Returns:**
- Dict with keys:
  - 'billed': Sum of total_amount (Decimal)
  - 'paid': Sum of annotated_paid (Decimal)

**Call Graph:**
```
Dashboard Cards showing total billed and paid:
    → InvoiceQuerySet.totals()
    → Displays overall revenue and payment metrics

InvoiceManager.get_dashboard_stats(user):
    → qs.totals()
    → returns dict with billed, paid, outstanding

InvoiceManager.get_total_outstanding(user):
    → .active().totals() 
    → calculates difference for outstanding balance

InvoiceManager.get_user_stats(user):
    → qs.with_totals().aggregate() similar pattern
```

**Note:** This is what the Dashboard Cards use for overall metrics

---

## InvoiceManager (invoices/managers.py)

### `update_totals(invoice)`

**Purpose:** Recalculates and updates all financial totals for an invoice. CRITICAL METHOD for maintaining invoice integrity.

**Called Whenever:**
- Line items (Items/Timesheets) are linked/unlinked
- Payments are added
- Invoice is saved
- Tax settings change

**Calculation Flow:**
1. Gather revenue from THREE sources (priority order):
   - billed_items (Items linked to invoice)
   - billed_timesheets (Timesheets linked to invoice, ONLY if no items)
   - custom_lines (Manual line items)
2. Calculate VAT based on user's tax registration status:
   - FULL mode: VAT on entire subtotal
   - MIXED mode: VAT only on taxable items
   - Not registered: No VAT
3. Auto-update status if payment completes invoice (PENDING → PAID)
4. Save all changes atomically

**Side Effects:**
- Updates: subtotal_amount, tax_amount, total_amount, status
- Calls invoice.save()
- May change status from PENDING to PAID if fully paid

**Call Graph:**
```
Signal handlers (items/signals.py, timesheets/signals.py):
    → When Item/Timesheet is linked/unlinked
    → InvoiceManager.update_totals(invoice)

Payment system (invoices/views.py):
    → When payments are added
    → InvoiceManager.update_totals(invoice)

Invoice save() override (invoices/models.py):
    → InvoiceManager.update_totals(self)

Dashboard calculations:
    → Relies on accurate totals from this method
```

---

### `get_total_outstanding(user)`

**Purpose:** Calculates total outstanding balance for a user across all active invoices.

**Calculation:** Outstanding = Total Billed - Total Paid for "active" invoices

**Returns:** Decimal - Amount user is owed by all clients combined

**Call Graph:**
```
Dashboard outstanding card:
    → InvoiceManager.get_total_outstanding(user)
    → Displays main "Outstanding" metric

User profile pages:
    → Shows total owed by all clients

Credit decisions and aging reports:
    → Uses this value to assess business performance
```

**Active Invoices:** Excludes DRAFT (not sent), CANCELLED, PAID (settled), and all Quotes.

---

### `get_dashboard_stats(user)`

**Purpose:** Gathers comprehensive invoice statistics for dashboard display.

**Returns:**
```python
{
    'total_billed': Decimal - Sum of ALL invoice totals
    'total_paid': Decimal - Sum of all payments received
    'total_outstanding': Decimal - total_billed minus total_paid
    'invoice_count': int - Total number of invoices (excluding quotes)
}
```

**Scope:** ALL invoices (not filtered like get_total_outstanding which excludes DRAFT/PAID).

**Call Graph:**
```
Dashboard main stats cards:
    → InvoiceManager.get_dashboard_stats(user)
    → Displays TOTAL revenue (all statuses)

Financial overview pages:
    → Shows comprehensive invoice summary

Revenue reporting:
    → Used for tax/accounting purposes
```

---

### `get_client_outstanding(client)`

**Purpose:** Calculates the outstanding balance owed BY a specific client.

**Returns:** Decimal - Outstanding balance (negative means client overpaid)

**Query Filters:**
- status IN (PENDING, OVERDUE) - unpaid invoices only
- date_issued and amount aggregated
- Excludes DRAFT, CANCELLED, PAID
- Excludes Quotes

**Call Graph:**
```
client_summary_detail.html Outstanding Balance card:
    → InvoiceManager.get_client_outstanding(client)
    → Displays "R1,944" style outstanding amount

clients/summary.py: ClientSummary.get_outstanding():
    → InvoiceManager.get_client_outstanding(client)
    → Used in progress calculations

Client payment tracking:
    → Identifies how much client still owes
    → Used for payment reminders/collections
```

---

### `get_user_stats(user)`

**Purpose:** Comprehensive invoice statistics for a user across all statuses.

**Returns:**
```python
{
    'billed': Decimal - Total amount invoiced across ALL statuses
    'paid': Decimal - Total amount paid (from PAID invoices)
    'outstanding': Decimal - Total still owed
}
```

**Scope:** ALL invoices (DRAFT, PENDING, OVERDUE, PAID) EXCEPT CANCELLED.

**Call Graph:**
```
User profile summary:
    → InvoiceManager.get_user_stats(user)

Business performance analysis:
    → Shows TOTAL BUSINESS ACTIVITY

Tax/accounting reports:
    → Uses for total revenue calculation

Year-end financial reporting:
    → Complete revenue picture
```

---

### `get_tax_summary(user)`

**Purpose:** Calculates VAT liability summary (collected vs paid to tax authority).

**Returns:**
```python
{
    'collected': Decimal - VAT collected from customers
    'paid': Decimal - VAT remitted to tax authority
    'outstanding': Decimal - Outstanding VAT liability
}
```

**Call Graph:**
```
Tax dashboard/reporting:
    → InvoiceManager.get_tax_summary(user)

VAT reconciliation:
    → Compares collected vs paid

Tax compliance tracking:
    → Ensures correct VAT remittance

Quarterly/annual tax submissions:
    → Provides authoritative VAT figures
```

**User Hierarchy:** If user.is_ops, includes stats for all assigned users.

**Data Sources:**
- Invoice.tax_amount from PAID invoices
- TaxPayment.amount records where tax_type='VAT'

---

### `get_client_invoices_before_date(client, before_date)`

**Purpose:** Calculates total outstanding from invoices issued BEFORE a specific date (for aging analysis).

**Use Case:** "How much from invoices over 30/60/90 days old?"

**Returns:** Decimal - Total outstanding from older invoices

**Call Graph:**
```
Accounts receivable aging reports:
    → InvoiceManager.get_client_invoices_before_date(client, cutoff_date)
    → Segmented by age buckets

Collection follow-up analysis:
    → Identifies old outstanding invoices

Invoice aging dashboard:
    → Shows age distribution of outstanding amounts
```

---

### `get_client_invoices_after_date(client, after_date)`

**Purpose:** Calculates total billed amount for invoices issued ON OR AFTER a specific date (for period reporting).

**Use Case:** "What was invoiced in this quarter/month?"

**Returns:** Decimal - Total invoice amount (includes paid + unpaid)

**Call Graph:**
```
Financial period reporting:
    → InvoiceManager.get_client_invoices_after_date(client, start_date)

Monthly/quarterly billing summaries:
    → Shows invoicing activity for period

Client invoicing history tracking:
    → Provides time-series data
```

---

## PaymentManager (invoices/managers.py)

### `get_invoice_total_paid(invoice)`

**Purpose:** Calculates total amount paid TOWARD a specific invoice.

**Returns:** Decimal - Total paid (0 if no payments)

**Call Graph:**
```
InvoiceManager.update_totals(invoice):
    → invoice.payments.aggregate(total=...) similar pattern
    → Used to calculate balance for status updates
    → Determines if invoice complete (PENDING → PAID)

Invoice detail pages:
    → Shows payment history and balance
    → Updates dynamic progress indicators

Outstanding calculation:
    → balance = total_amount - paid
```

---

### `get_client_total_paid(client)`

**Purpose:** Calculates total amount paid BY a specific client across all their invoices.

**Returns:** Decimal - Total received from client (all-time)

**Call Graph:**
```
client_summary_detail.html Payments card:
    → Displays total received from this client

clients/summary.py: ClientSummary.get_payments():
    → PaymentManager.get_client_total_paid(client)

Client relationship analytics:
    → Shows payment reliability
    → Historical payment volume
```

---

### `get_user_total_received(user)`

**Purpose:** Calculates total revenue collected by a user from all invoices.

**Returns:** Decimal - Total revenue received (all-time, all clients/invoices)

**Call Graph:**
```
Dashboard Payments card:
    → InvoiceManager.get_dashboard_stats(user) similar pattern
    → Displays "Total Payments" metric

Financial summary and KPI tracking:
    → Shows cash collected over time

Income statement line items:
    → Primary revenue figure
    → Used for business profitability analysis
```

---

## Summary Call Graph

### High-Level Data Flow

```
User Dashboard
    ├── ClientSummary.get_items() → Item.get_unprocessed_value() → progress bar
    ├── ClientSummary.get_timesheets() → Timesheet.get_unprocessed_value() → progress bar
    ├── InvoiceManager.get_dashboard_stats() → QuerySet.totals() → stats cards
    ├── InvoiceManager.get_total_outstanding() → QuerySet.active().totals() → outstanding
    └── PaymentManager.get_user_total_received() → total payments

Client Detail Page
    ├── InvoiceManager.get_client_outstanding() → outstanding balance
    ├── Item.get_unprocessed_value() → items progress card
    ├── Timesheet.get_unprocessed_value() → timesheets progress card
    └── PaymentManager.get_client_total_paid() → total received from client

Invoice Creation Flow
    ├── Item.can_be_invoiced(ids) → validation before creation
    ├── Item.get_unprocessed() → queryset for form selection
    ├── [Create Invoice]
    ├── InvoiceManager.update_totals() → recalculate amounts and VAT
    └── [Invoice saved]

Payment Recording
    ├── Payment.create()
    ├── InvoiceManager.update_totals() → recalculate balance and status
    └── Auto-status PENDING → PAID if fully paid

Tax Reporting
    ├── InvoiceManager.get_tax_summary() → VAT collected/paid
    ├── InvoiceManager.get_tax_year_report() → annual revenue
    └── TaxPayment.create() → record SARS payments
```

---

## Dependencies and Relationships

- **ItemManager and TimesheetManager** are parallel implementations for two different content types
- **InvoiceQuerySet** provides base filtering used by InvoiceManager methods  
- **PaymentManager** depends on related payments and is called by InvoiceManager.update_totals()
- **ClientSummary** (clients/summary.py) is the main aggregator that calls all these manager methods for display
- **Dashboard** and templates depend on accurate calculations from all these managers

---

## Business Rules Enforced

1. **Items/Timesheets are "processed" when linked to an invoice** (invoice_id is not NULL)
2. **Can only invoice unprocessed items** (can_be_invoiced checks this)
3. **Invoice totals are always calculated from source data** (update_totals enforces accuracy)
4. **Status auto-transitions PENDING → PAID** when fully paid (update_totals checks this)
5. **VAT is calculated based on tax registration status** (update_totals checks user profile)
6. **Cancelled invoices are immutable** (update_totals returns early for CANCELLED)
7. **All financial calculations use Decimal type** for accuracy (never float for money)

---

## Performance Considerations

- **Subqueries:** with_totals() uses Subquery for payment aggregation (more efficient than N+1 queries)
- **Aggregation:** All totals calculations done at database level using Sum/aggregate
- **Filtering:** Manager methods filter early in QuerySet chain before aggregation
- **Caching:** Consider database query result caching for frequently accessed stats

