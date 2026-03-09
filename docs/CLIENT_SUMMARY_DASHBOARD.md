# Client Summary Dashboard

## Overview

The Client Summary Dashboard provides a comprehensive view of all client-related data aggregated by client. It allows you to see quotes, timesheets, items, invoices, and other metrics at a glance, with the ability to drill down into individual client details.

## Features

### Dashboard View (`/clients/summary/`)

The main dashboard displays:

- **Total Clients Count** - Number of active clients
- **Quotes Summary** - Total count and value of all quotes
- **Timesheets Summary** - Total count, hours, and value of timesheets
- **Items Summary** - Total count and value of items
- **Invoices Summary** - Total count and value of all invoices
- **Outstanding Balance** - Total unpaid invoices across all clients

**Table View**: Shows each client with:
- Quote count and value (by status: pending, accepted, rejected)
- Timesheet count and value (by status: billed, unbilled)
- Item count and value (by status: billed, unbilled)
- Invoice count and value (by status: draft, pending, overdue, paid, cancelled)
- Outstanding balance for that client
- Quick link to drill-down view

### Detailed Client View (`/clients/summary/<client_id>/`)

Clicking "Details" on a client row shows a detailed breakdown with separate sections for:

#### Quotes Section
- Pending quotes (count and total value)
- Accepted quotes (count and total value)
- Rejected quotes (count and total value)
- Total across all statuses

#### Timesheets Section
- Billed timesheets (count, hours, and total value)
- Unbilled timesheets (count, hours, and total value)
- Total across all statuses

#### Items Section
- Billed items (count and total value)
- Unbilled items (count and total value)
- Total across all statuses

#### Invoices Section
- Draft invoices (count and value)
- Pending invoices (count and value)
- Overdue invoices (count and value)
- Paid invoices (count and value)
- Cancelled invoices (count and value)
- Total across all statuses

#### Email Status Section
- Emailed invoices (count and value)
- Not emailed invoices (count and value)

#### Client Information
- Client name and contact
- Email address
- Phone number
- Client code
- Payment terms

## Navigation

### From Dashboard

From the main Business Dashboard, click the **"Client Summary"** button in the top right to access the summary dashboard.

### From Client List

The Client Summary Dashboard is accessible from the main navigation as a separate view.

## Data Calculation Rules

The summary data follows these rules to ensure consistency:

### Quotes
- **Included**: All invoices with `is_quote=True`
- **Status Breakdown**: 
  - Pending: `quote_status='PENDING'`
  - Accepted: `quote_status='ACCEPTED'`
  - Rejected: `quote_status='REJECTED'`
- **Excluded**: Cancelled quotes are not included

### Timesheets
- **Included**: All timesheet entries for the client
- **Billed**: `is_billed=True`
- **Unbilled**: `is_billed=False`
- **Value Calculation**: Hours × Hourly Rate for each entry, then summed

### Items
- **Included**: All items for the client
- **Billed**: `is_billed=True`
- **Unbilled**: `is_billed=False`
- **Value Calculation**: Quantity × Unit Price for each item, then summed

### Invoices
- **Included**: All invoices with `is_quote=False`
- **Status Breakdown**: DRAFT, PENDING, OVERDUE, PAID, CANCELLED
- **Excluded**: Quotes (`is_quote=True`) are never counted

### Outstanding Balance
- **Calculation**: Sum of (Invoice Total - Total Paid) for all PENDING and OVERDUE invoices
- **Excluded**: DRAFT, PAID, CANCELLED, and QUOTE invoices

### Email Status
- **Included**: All non-quote invoices
- **Emailed**: `is_emailed=True`
- **Not Emailed**: `is_emailed=False`

## Implementation Details

### New Files Created

1. **`clients/summary.py`**
   - `ClientSummary` class: Provides summary data for a single client
   - `AllClientsSummary` class: Aggregates data across all clients
   
2. **`clients/views.py` (updated)**
   - `clients_summary_dashboard()`: Main dashboard view showing all clients
   - `client_summary_detail()`: Detailed view for individual client

3. **`clients/urls.py` (updated)**
   - Route: `summary/` → `clients_summary_dashboard`
   - Route: `summary/<int:pk>/` → `client_summary_detail`

4. **Templates**
   - `clients/templates/clients/clients_summary_dashboard.html`: Main dashboard
   - `clients/templates/clients/client_summary_detail.html`: Detailed view

## Usage Example

```python
from clients.models import Client
from clients.summary import ClientSummary, AllClientsSummary

# Get summary for a single client
client = Client.objects.get(pk=1)
summary = ClientSummary(client).get_summary()

print(summary['quotes']['total_count'])        # Total number of quotes
print(summary['timesheets']['total_value'])   # Total value of timesheets
print(summary['invoices']['pending']['count']) # Number of pending invoices
print(summary['outstanding']['total'])         # Outstanding balance

# Get summaries for all clients
all_summaries = AllClientsSummary(user)
summaries = all_summaries.get_all_summaries()  # List of all client summaries
totals = all_summaries.get_totals()            # Aggregated totals across all clients
```

## Color Coding

The dashboard uses color coding to distinguish different data types:

- **Blue** - Quotes and general information
- **Primary Blue** - Timesheets
- **Green** - Items
- **Gray** - Invoices
- **Yellow/Orange** - Email status
- **Red** - Outstanding/Warning information

## Performance Considerations

The summary functions perform database queries per record to calculate totals (e.g., for timesheets and items). For clients with very large numbers of records, this could be slow. If performance becomes an issue, consider:

1. Caching the summary data
2. Using raw SQL aggregations with F expressions
3. Implementing pagination for large result sets

## Related Features

This dashboard integrates with:
- **Client List**: Manage clients
- **Client Statement**: View financial transactions
- **Invoice Management**: Create and track invoices
- **Timesheet Tracking**: Log and bill work hours
- **Item Management**: Track billable items

