# Reconciliation Statements - User Guide

## Overview

The reconciliation statements system provides comprehensive tracking of client balances, including:
- **Individual client reconciliation statements** with detailed transaction history
- **All clients summary** showing outstanding balances and credit positions across your entire client base
- **Cancelled invoice tracking** for auditing purposes
- **Credit note management** for overpayments and manual adjustments

---

## Features

### 1. Client Reconciliation Statement

View a complete reconciliation for any client showing:

#### Summary Section
- **Opening Balance**: Starting position at beginning of period
- **Invoices Sent**: Total of invoices issued in period
- **Invoices Cancelled**: Reversal of cancelled invoices (shown separately)
- **Payments Received**: Total payments collected
- **Credit Notes Issued**: Adjustments for overpayments/discounts
- **Closing Balance**: Final position (what client owes)

#### Transaction Details
Line-by-line view of all movements:
- Invoice issuance
- Payments received
- Credit notes applied
- Cancelled invoices (with reasons)

Each transaction shows:
- Date
- Type (Invoice/Payment/Credit/Cancellation)
- Description and reference
- Amount
- Running balance

#### Cancelled Invoices Section
Special highlighting of invoices that were:
1. Successfully sent to the client
2. Later cancelled
Shows the cancellation reason for audit trail

#### Outstanding Credit
Displays total credit balance available for this client to apply against future invoices

### 2. All Clients Reconciliation

Executive summary showing all clients:
- Outstanding balance (unpaid invoices)
- Total payments (cumulative)
- Available credit balance
- Cancelled invoices that were sent
- Total invoices issued

**Quick stats cards** at top show:
- Total outstanding across all clients
- Total payments received
- Total credit issued
- Net position

**Table format** allows sorting by:
- Client name
- Outstanding amount
- Payment history
- Credit available
- Invoice count

---

## Credit Notes System

### Creating Credit Notes

Credit notes can be created via Django Admin for three scenarios:

#### 1. Overpayment Credits
When a client pays more than invoiced (currently manual since Payment model prevents overpaying):
1. Go to Admin → Invoices → Credit Notes
2. Click "Add Credit Note"
3. Select client and related invoice
4. Choose type: **OVERPAYMENT**
5. Enter amount paid above invoice total
6. Save

#### 2. Manual Adjustments/Discounts
For operational adjustments or discounts given:
1. Go to Admin → Invoices → Credit Notes
2. Click "Add Credit Note"
3. Select client (invoice optional)
4. Choose type: **ADJUSTMENT**
5. Enter adjustment amount
6. Add description (optional)
7. Save

#### 3. Cancelled Invoice Credits
When an invoice was cancelled but client was already charged:
1. Go to Admin → Invoices → Credit Notes
2. Click "Add Credit Note"
3. Select client and the cancelled invoice
4. Choose type: **CANCELLATION**
5. Enter the invoice amount
6. Save

### Credit Note Fields

- **Reference**: Unique identifier (e.g., CN2026-001) - helpful for tracking
- **Amount**: Total credit value
- **Balance**: Remaining credit available (auto-calculated)
- **Issued Date**: When credit was issued
- **Description**: Why credit was issued (appears in recon statement)
- **Note Type**: OVERPAYMENT | ADJUSTMENT | CANCELLATION | OTHER

As credits are applied to future invoices, the **Balance** field decreases.

---

## How to Access Reconciliation Statements

### From Dashboard
1. Navigate to Invoices → Dashboard
2. Look for "Reconciliation" link in sidebar (coming soon)

### Direct URLs
```
/invoices/reconciliation/                          # All clients summary
/invoices/reconciliation/client/<client_id>/       # Single client statement
```

### Via Client List
1. Go to Clients
2. Click three-dot menu on any client
3. Select "View Reconciliation"

---

## Exporting Reconciliation Data

### All Clients Summary

**Export as CSV:**
- Click "Export CSV" button
- Shows all clients with summary data
- Includes totals row
- Can be opened in Excel/Sheets

### Client Reconciliation

**Three export options:**

1. **CSV Export**
   - Click "CSV" download button
   - Contains summary + full transaction list
   - Best for importing to accounting software

2. **PDF Export** (if reportlab installed)
   - Click "PDF" download button
   - Professional format for client or internal use
   - Includes summary and transaction details

3. **HTML View**
   - Click "Filter" to apply date range
   - Print to PDF from browser (Ctrl+P / Cmd+P)
   - View with all styling

---

## Date Range Filtering

### All Clients Statement
- **As at Date**: View position as of specific date
- Default: Today's date
- Change date and click "Filter" to recalculate

### Client Statement
- **Start Date**: (Optional) Beginning of period
  - Leave blank to show from beginning of time
- **End Date**: End of period (default: today)
- Both dates inclusive
- Click "Filter" to recalculate

---

## Reconciliation Logic

### Opening Balance Calculation
- Sum of unpaid invoices issued before period start
- Minus: Payments made before period
- Minus: Credits issued before period

### Transaction Ordering
All movements shown chronologically by date:
1. Invoices (sorted by issue date)
2. Payments (sorted by payment date)
3. Credit notes (sorted by issue date)
4. Cancelled invoices (reverse entry)

### Closing Balance
```
Closing = Opening + Invoices - Cancellations - Payments - Credits
```

### Outstanding Balance
Only includes invoices with status:
- PENDING (sent but not yet paid)
- OVERDUE (past due date)

Excludes:
- DRAFT (not yet sent)
- CANCELLED (reversed out)
- PAID (collected)

---

## Common Use Cases

### Case 1: Client Claims They Overpaid
1. Open client reconciliation
2. Look through Transaction Details table
3. Verify all payments logged correctly
4. If genuine overpayment:
   - Create credit note with type OVERPAYMENT
   - Reference the excessive payment in description
   - Credit available for deduction from next invoice

### Case 2: Cancelled Invoice After Payment
1. Create credit note with type CANCELLATION
2. Link to the cancelled invoice
3. Set amount = invoice amount
4. This way, if client paid before cancellation, they have credit balance

### Case 3: Quarterly Reconciliation
1. Go to All Clients Reconciliation
2. Change "As at Date" to quarter-end date
3. Export to CSV
4. Review for any outstanding credits or disputed amounts
5. Follow up on large outstanding balances

### Case 4: Discount/Adjustment
1. Create credit note with type ADJUSTMENT
2. No invoice needed
3. Describe reason (e.g., "Early payment discount", "Volume rebate")
4. Amount automatically available for client

---

## Admin Interface

### Managing Credit Notes

**In Admin → Invoices → Credit Notes:**

**List View** shows:
- Reference number
- Client
- Amount
- Remaining balance
- Type
- Issue date

**Filtering** by:
- Type (adjust, overpayment, cancellation, etc.)
- Date range
- Client

**Add New** - Click "Add Credit Note":
1. Select client
2. Optionally link to invoice
3. Choose type
4. Enter amount and issued date
5. Add optional description & reference
6. Save

**Edit** - Click any credit note:
- Update description
- Adjust issued date (not usually recommended)
- Note: Balance field is read-only (calculates automatically)

**Delete** - Carefully!
- Deleting a credit note increases client's outstanding balance
- Best practice: Only delete for data entry errors, not reversals

---

## Cancelled Invoice Handling

### Cancelled But Not Sent
- Not shown in reconciliation
- No credit note needed
- Clean reversals of draft invoices

### Cancelled After Sending
- **Highlighted** in "Cancelled Invoices (Previously Sent)" section
- Reason tracked in `invoice.cancellation_reason`
- Usually needs credit note if payment already received
- Reversal shown as negative amount in transaction list

---

## Key Metrics

### Per-Client Metrics
- **Outstanding Balance**: Action item if overdue
- **Credit Balance**: Shows cash tied up in adjustments/overpayments
- **Cancelled Sent**: Auditing metric - should be minimal

### Firm-Wide Metrics
- **Total Outstanding**: Cash flow indicator - how much to collect
- **Total Payments**: Revenue recognition - cumulative collected
- **Total Credits**: Liability - unused client credit available

---

## Best Practices

1. **Monthly Review**
   - Generate all clients summary on month-end
   - Export and file with accounting
   - Flag any unusual balances

2. **Credit Note Discipline**
   - Always use proper type (don't default to "OTHER")
   - Include clear reference for traceability
   - Link to invoice when applicable

3. **Discrepancy Investigation**
   - Use detailed client reconciliation
   - Check email status logs for delivery issues
   - Verify payment references match invoice numbers

4. **Documentation**
   - Update cancellation reason when cancelling invoice (required)
   - Add description to credit notes
   - Use reference field for cross-referencing support tickets

5. **System Maintenance**
   - Quarterly review of credit balances
   - Process aged credits (> 6 months)
   - Archive old reconciliations

---

## Technical Details

### Included in Reconciliation
✅ Active invoices (PENDING, PAID, OVERDUE)
✅ Cancelled invoices that were sent (is_emailed=True)
✅ All payments linked to invoices
✅ All credit notes issued to client

### Excluded from Reconciliation
❌ Draft invoices (not yet sent)
❌ Cancelled invoices never sent
❌ Payments not linked to invoices
❌ Unprocessed payment attempts

### Data Sources
- `Invoice` model (status, amount, dates)
- `Payment` model (amount,reference)
- `CreditNote` model (amount, type, reason)
- `InvoiceEmailStatusLog` (delivery tracking)

---

## Troubleshooting

### "Closing Balance doesn't match my manual calculation"
- Verify date range is correct
- Check for draft invoices (should be excluded)
- Look at Cancelled section - reversals may not be obvious
- Review Credit Notes section for unexpected adjustments

### "Credit balance shows but I haven't issued any credits"
- Check if payment exceeded invoice amount manually
- Review admin for auto-generated credit notes
- Look at payment records for duplicate entries

### "Cancelled invoices not showing"
- Verify `is_emailed` flag is true
- Check if cancelled after sending (not before)
- Invoice must have `status = 'CANCELLED'`

### PDF export not working
- Reportlab library may not be installed
- Try CSV or HTML export instead
- See admin to install: `pip install reportlab`

---

## Future Enhancements

Potential additions:
- [ ] Automatic credit note creation on overpayment
- [ ] Email reconciliation statements to clients
- [ ] Payment plan tracking
- [ ] Aging analysis (30/60/90+ days)
- [ ] Credit note batch processing
- [ ] Recurring credit allocations

---

For questions or issues, contact your system administrator.
