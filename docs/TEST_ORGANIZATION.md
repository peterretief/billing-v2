# Test Organization Guide

Tests are now organized by category in `/invoices/tests/` directory for easy discovery and management.

## Directory Structure

```
invoices/tests/
├── __init__.py
├── test_billing.py         # Billing calculation tests
├── test_dashboard.py       # Dashboard total calculation tests
└── test_payments.py        # Payment validation tests
```

## How to Run Tests

### Run All Tests
```bash
python manage.py test invoices.tests
```

### Run Specific Test Suite

**Billing Tests** (1 test)
```bash
python manage.py test invoices.tests.test_billing
```

**Dashboard Tests** (6 tests)
```bash
python manage.py test invoices.tests.test_dashboard
```

**Payment Tests** (5 tests)
```bash
python manage.py test invoices.tests.test_payments
```

### Run Specific Test Class

```bash
python manage.py test invoices.tests.test_billing.BillingLogicTest
python manage.py test invoices.tests.test_dashboard.DashboardTotalsTest
python manage.py test invoices.tests.test_payments.PaymentValidationTest
```

### Run Specific Test Method

```bash
python manage.py test invoices.tests.test_billing.BillingLogicTest.test_standard_timesheet_billing
python manage.py test invoices.tests.test_dashboard.DashboardTotalsTest.test_unbilled_timesheet_calculation
python manage.py test invoices.tests.test_payments.PaymentValidationTest.test_payment_exceeds_balance_rejected
```

### Run with Verbose Output
```bash
python manage.py test invoices.tests -v 2
```

## Test Summary

| File | Class | Tests | Purpose |
|------|-------|-------|---------|
| `test_billing.py` | `BillingLogicTest` | 1 | Standard invoice item billing calculations |
| `test_dashboard.py` | `DashboardTotalsTest` | 6 | Dashboard unbilled totals (timesheets + items) |
| `test_payments.py` | `PaymentValidationTest` | 5 | Payment validation & overpayment prevention |

**Total:** 12 tests ✅

## Test Details

### Billing Tests (test_billing.py)
- ✅ `test_standard_timesheet_billing` - Verifies invoice item calculations

### Dashboard Tests (test_dashboard.py)
- ✅ `test_unbilled_timesheet_calculation` - Unbilled timesheet totals
- ✅ `test_unbilled_items_calculation` - Unbilled item totals
- ✅ `test_combined_unbilled_total` - Combined timesheet + item totals
- ✅ `test_billed_items_excluded` - Billed items not included in totals
- ✅ `test_other_user_data_excluded` - Multi-tenant data isolation
- ✅ `test_empty_dashboard_totals` - Zero state handling

### Payment Tests (test_payments.py)
- ✅ `test_payment_under_balance_succeeds` - Partial payments accepted
- ✅ `test_payment_equal_to_balance_succeeds` - Full payments accepted
- ✅ `test_payment_exceeds_balance_rejected` - Overpayments prevented
- ✅ `test_zero_payment_rejected` - Zero/negative payments rejected
- ✅ `test_multiple_partial_payments` - Multiple payments accumulate correctly

## Quick Commands

```bash
# Run all invoice tests
python manage.py test invoices.tests

# Run only billing tests
python manage.py test invoices.tests.test_billing

# Run only dashboard tests
python manage.py test invoices.tests.test_dashboard

# Run only payment tests
python manage.py test invoices.tests.test_payments

# Run with verbose output
python manage.py test invoices.tests -v 2
```
