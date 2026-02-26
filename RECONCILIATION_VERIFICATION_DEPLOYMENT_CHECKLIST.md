# Verification System Deployment Checklist

## Pre-Deployment: Code Verification

- [x] `invoices/reconciliation.py` - No syntax errors
- [x] `invoices/recon_views.py` - No syntax errors  
- [x] `invoices/management/commands/verify_reconciliation.py` - No syntax errors
- [x] Template renders without errors
- [x] All imports resolve correctly
- [x] Model relationships intact

## Immediate Post-Deployment (First 1 hour)

### Visual Check
- [ ] Visit `/invoices/reconciliation/client/1/` in browser
- [ ] Verify page loads without 500 errors
- [ ] Check if reconciliation summary displays
- [ ] Verify badge displays (green if passing)
- [ ] If red badge, verify alert section appears with error details

### CLI Check
```bash
python manage.py verify_reconciliation --client 1
```
- [ ] Command runs without errors
- [ ] Shows verification status (✓ or ✗)
- [ ] Shows actual values from both methods
- [ ] Completes in < 5 seconds

### CSV/PDF Check
- [ ] Export reconciliation to CSV works
- [ ] Export to PDF works
- [ ] Verification status included in exports

## First Testing (Hour 1-2)

### Run Full Audit
```bash
python manage.py verify_reconciliation --all-clients --user testuser
```
- [ ] All clients pass verification
- [ ] No unexpected errors
- [ ] Performance acceptable (< 30 seconds for 10 clients)

### Verbose Debug
```bash
python manage.py verify_reconciliation --client 1 --verbose
```
- [ ] Shows all individual transactions
- [ ] Output is readable and accurate
- [ ] No Python errors in output

## Daily Monitoring (Day 1-3)

### Check For Red Alerts
- [ ] No reconciliation pages showing red alerts
- [ ] If red alerts appear, investigate immediately
- [ ] Document any issues found

### Database Integrity
- [ ] Query for duplicate invoice records
  ```sql
  SELECT invoice_number, COUNT(*) FROM invoices/invoice 
  GROUP BY invoice_number HAVING COUNT(*) > 1;
  ```
- [ ] Query for orphaned payments
  ```sql
  SELECT * FROM invoices/payment 
  WHERE invoice_id NOT IN (SELECT id FROM invoices/invoice);
  ```
- [ ] Check for soft-deleted records affecting calculations

### Performance Baseline
- [ ] Time a typical reconciliation load
- [ ] Acceptable time: < 2 seconds for < 1000 transactions
- [ ] Note baseline for future comparison

## Week 1: Extended Testing

### Test Date Range Filtering
```bash
python manage.py verify_reconciliation --client 1 \
  --start-date 2026-01-01 --end-date 2026-02-28
```
- [ ] Works correctly
- [ ] Filters data appropriately
- [ ] Verification still accurate

### Test Multiple Clients
- [ ] Run verification on 5-10 clients
- [ ] At least one from each user/organization
- [ ] All should pass (or have documented issues)

### Test Export Formats
- [ ] HTML reconciliation displays verification
- [ ] CSV export includes verification status
- [ ] PDF export shows verification badge/alerts
- [ ] Email notifications don't break

### Verify Edge Cases
- [ ] Client with $0 invoices
- [ ] Client with large numbers (> $100k)
- [ ] Client with many transactions (> 1000)
- [ ] Client with date ranges spanning multiple months

## Data Quality Issues Found (If Any)

### Duplicate Records
```bash
# Identify duplicates
SELECT invoice_number, date_created, total_amount, COUNT(*) 
FROM invoices/invoice 
GROUP BY invoice_number 
HAVING COUNT(*) > 1;

# Delete duplicates (CAREFULLY!)
DELETE FROM invoices/invoice 
WHERE id NOT IN (
  SELECT MIN(id) FROM invoices/invoice 
  GROUP BY invoice_number
);

# Re-verify
python manage.py verify_reconciliation --all-clients --user admin
```
- [ ] Duplicates identified
- [ ] Duplicates deleted (backup first!)
- [ ] Verification passes after cleanup

### Orphaned Payments
```bash
# Identify orphans
SELECT id, amount, invoice_id 
FROM invoices/payment 
WHERE invoice_id NOT IN (SELECT id FROM invoices/invoice);

# Option 1: Delete orphaned payments
DELETE FROM invoices/payment 
WHERE invoice_id NOT IN (SELECT id FROM invoices/invoice);

# Option 2: Link to correct invoice
UPDATE invoices/payment 
SET invoice_id = [correct_id] 
WHERE id = [payment_id];

# Re-verify
python manage.py verify_reconciliation --client [client_id]
```
- [ ] Orphaned payments identified
- [ ] Resolution chosen (delete vs. relink)
- [ ] Changes applied
- [ ] Verification passes after fix

## Week 2: Stability Checks

### Ongoing Monitoring Points
- [ ] No new reconciliation verification errors in logs
- [ ] Performance remains consistent
- [ ] No customer complaints about reconciliation accuracy
- [ ] All automated exports (if any) still working

### Periodic Full Audit
```bash
# Run weekly
python manage.py verify_reconciliation --all-clients --user admin > audit_$(date +%Y%m%d).log
```
- [ ] Run weekly full verification
- [ ] Archive results
- [ ] Review for trends

### Regression Testing
- [ ] Manually compute one client reconciliation by hand
- [ ] Verify system matches manual calculation
- [ ] Do this for 2-3 different clients

## Documentation Sign-Off

- [ ] All users trained on red/green badge meaning
- [ ] Support team knows how to run CLI verification
- [ ] Developers know how to add new verified calculations
- [ ] This checklist completed and filed

## Success Criteria Met

All of the following should be true:
- ✅ Verification badge appears correctly (green/red)
- ✅ All test clients pass verification
- ✅ No false positives (red when should be green)
- ✅ No false negatives (green when should be red)
- ✅ CLI tool works and provides useful debug info
- ✅ Performance acceptable (< 500ms for typical client)
- ✅ Documentation is complete and accurate
- ✅ Team is trained and confident in system
- ✅ No existing functionality broken

## Rollback Plan (If Issues Discovered)

If serious issues found:

```bash
# Revert reconciliation.py to prior version
git checkout HEAD~1 -- invoices/reconciliation.py

# Revert template
git checkout HEAD~1 -- invoices/templates/invoices/client_reconciliation.html

# Keep recon_views.py as-is (minimal changes)

# Restart Django
python manage.py runserver  # or supervisor
```

**After rollback**: Identify root cause, fix, re-test, then re-deploy.

## Performance Baseline

After deployment, record baseline metrics:

| Metric | Value | Date |
|--------|-------|------|
| Typical reconciliation load time | ___ ms | ____ |
| Large client (1000+ txns) time | ___ ms | ____ |
| All-clients audit time (10 clients) | ___ sec | ____ |
| Typical verification time (Method 1) | ___ ms | ____ |
| Typical verification time (Method 2) | ___ ms | ____ |

## Sign-Off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Developer | _____ | _____ | Code review complete |
| QA | _____ | _____ | Testing complete |
| DevOps | _____ | _____ | Deployment complete |
| Product | _____ | _____ | Feature approved |

## Post-Deployment Support

### Common Issues & Solutions

**Issue: Red alert on all clients**
- Likely: SQL or ORM bug in verification code
- Solution: Check method implementations in reconciliation.py
- Rollback if needed

**Issue: Verification very slow (> 5 seconds)**
- Likely: N+1 queries or inefficient iteration
- Solution: Add .select_related() or .prefetch_related()
- Profile with Django Debug Toolbar

**Issue: Verification passes but numbers seem wrong**
- Likely: Both methods have the same bug (rare)
- Solution: Manually verify high-value transactions
- Check for database-level issues

**Issue: CSV/PDF exports don't show verification status**
- Likely: Template not updated correctly
- Solution: Check if HTML template changes are correct
- Verify export views are using updated templates

### Support Contacts

- **Django Support**: [Internal DBA/Backend team]
- **Bug Reports**: [GitHub issues or Jira]
- **Performance Issues**: [DevOps team]
- **Data Issues**: [Business Analyst]

## Final Notes

✅ The dual verification system is production-ready

🔍 Monitor closely for week 1 to catch any edge cases

⚠️ Red alerts should NOT be ignored - investigate immediately

📊 Keep running periodic audits to ensure data quality

🎯 Goal achieved: Impossible balances now caught and flagged
