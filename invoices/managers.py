#import profile
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.db.models import DecimalField, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


class InvoiceQuerySet(models.QuerySet):
    """
    Base QuerySet for Invoice model providing common filtering and calculation patterns.
    
    Used to build up complex queries for invoices with related payment data without
    having to repeat these patterns throughout views and managers.
    """
    
    def with_totals(self):
        """
        Annotates queryset with aggregated payment totals for each invoice.
        
        Key Pattern: Uses Subquery to safely aggregate related Payment objects,
        handling cases where no payments exist (returns 0.00).
        
        Returns: QuerySet with additional 'annotated_paid' field containing total payments
        
        Used By:
            - InvoiceManager methods that need payment information
            - All places calculating outstanding balances (paid vs total_amount)
            
        SQL: Subquery on payments table grouped by invoice, coalesced to 0 if NULL
        """
        from .models import Payment

        # Subquery to sum payments for each invoice
        pay_sub = (
            Payment.objects.filter(invoice=OuterRef("pk"))
            .values("invoice")
            .annotate(total=Sum("amount"))
            .values("total")
        )

        return self.annotate(annotated_paid=Coalesce(Subquery(pay_sub, output_field=DecimalField()), Decimal("0.00")))

    def active(self):
        """
        Filters to "active" invoices (those with outstanding balance).
        
        Exclusions: DRAFT, CANCELLED, PAID statuses and all Quotes
        
        Business Context: Used for calculating outstanding balances since these statuses
        don't represent money owed - drafts aren't sent, cancelled/paid are settled.
        
        Returns: Filtered QuerySet
        
        Used By:
            - get_total_outstanding() for dashboard outstanding amount
            - Dashboard calculations for outstanding balance
        """
        # Exclude Drafts, Cancelled, Paid, and Quotes from Outstanding math
        # Must chain excludes because .exclude(a__in=[...], b=True) only excludes where BOTH are true
        return self.exclude(status__in=["DRAFT", "CANCELLED", "PAID"]).exclude(is_quote=True)

    def totals(self):
        """
        Aggregates total billed and total paid amounts for the queryset.
        
        Key Calculation: Uses with_totals() to get annotated_paid, then aggregates
        both total_amount (billed) and annotated_paid (collected payments).
        
        Exclusions: Excludes all Quotes (is_quote=False filter) and DRAFT invoices
        
        Returns: Dict with keys:
            - 'billed': Sum of total_amount (Decimal)
            - 'paid': Sum of annotated_paid (Decimal)
            
        Used By:
            - Dashboard Cards showing total billed and paid
            - InvoiceManager.get_user_stats() for user statistics
            - Client payment tracking
            
        Note: This is what the Dashboard Cards use for overall metrics
        """
        # This is what the Dashboard Cards use (exclude quotes and DRAFT)
        return self.exclude(is_quote=True).exclude(status="DRAFT").with_totals().aggregate(
            billed=Coalesce(Sum("total_amount"), Decimal("0.00")),
            paid=Coalesce(Sum("annotated_paid"), Decimal("0.00")),
        )


class InvoiceManager(models.Manager.from_queryset(InvoiceQuerySet)):
    """
    Manager for Invoice model consolidating all invoice-related business logic and calculations.
    
    Key Responsibilities:
    1. Total calculations (revenue, outstanding, paid)
    2. Status management (DRAFT, PENDING, PAID, CANCELLED, OVERDUE)
    3. Tax calculations (VAT collected, outstanding tax, tax year reporting)
    4. Client and user-level aggregations
    """
    
    def update_totals(self, invoice):
        """
        Recalculates and updates all financial totals for an invoice.
        
        This is a CRITICAL method that maintains invoice integrity. It's called whenever
        line items or payments change to ensure the invoice total_amount is always accurate.
        
        Calculation Flow:
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
        
        Parameters:
            invoice (Invoice): The invoice object to recalculate
            
        Side Effects:
            - Updates: subtotal_amount, tax_amount, total_amount, status
            - Calls invoice.save()
            - May change status from PENDING to PAID if fully paid
            
        Guard Clause: Does nothing if invoice.status == "CANCELLED" (cancelled invoices are immutable)
        
        Used By:
            - Signal handlers when items/timesheets are linked/unlinked
            - Payment system when payments are added
            - Invoice save() override
            - Dashboard calculations that need fresh data
        """

        profile = getattr(invoice.user, 'profile', None)
        # Ensure profile is fresh from DB to get latest VAT settings
        if profile:
            profile.refresh_from_db()
        is_registered = getattr(profile, "is_vat_registered", False)
        custom_vat_rate = getattr(profile, "vat_rate", None) or Decimal("15.00")

        subtotal = Decimal("0.00")

        # A. Primary Source: Billed Items
        has_items = False
        if hasattr(invoice, "billed_items") and invoice.billed_items.exists():
            items = invoice.billed_items.all()
            subtotal += sum((item.quantity * item.unit_price for item in items), Decimal("0.00"))
            has_items = True

        # B. Fallback Source: Timesheets
        if not has_items and hasattr(invoice, "billed_timesheets"):
            timesheets = invoice.billed_timesheets.all()
            subtotal += sum((ts.hours * ts.hourly_rate for ts in timesheets), Decimal("0.00"))

        # C. Custom Items
        if hasattr(invoice, "custom_lines"):
            subtotal += sum((line.total for line in invoice.custom_lines.all()), Decimal("0.00"))

        # Tax Calculation - simple: if user is VAT registered, apply VAT to all items
        tax_amount = Decimal("0.00")
        if is_registered:
            rate = custom_vat_rate / Decimal("100.00")
            tax_amount = subtotal * rate

        # Quantize all values to 2 decimal places to match DecimalField requirements
        invoice.subtotal_amount = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        invoice.tax_amount = tax_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        invoice.total_amount = (invoice.subtotal_amount + invoice.tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Status Sync — calculate balance directly from DB payments
        # to avoid stale in-memory values
        from django.db.models import Sum

        total_paid = invoice.payments.aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]

        balance = invoice.total_amount - total_paid

        # Only auto-change to PAID if:
        # 1. Invoice is PENDING
        # 2. Invoice has a non-zero total (not just created empty)
        # 3. Balance is fully paid (balance <= 0)
        if invoice.status == "PENDING" and invoice.total_amount > 0 and balance <= 0:
            invoice.status = "PAID"

        invoice.save(update_fields=["subtotal_amount", "tax_amount", "total_amount", "status"])

    def get_total_outstanding(self, user):
        """
        Calculates total outstanding balance for a user across all active invoices.
        
        Business Logic: Outstanding = Total Billed - Total Paid for "active" invoices
        
        Active Invoices: Excludes DRAFT (not sent), CANCELLED, PAID (settled), and all Quotes.
        This prevents double-counting money in multiple states.
        
        Calculation: Uses .active().totals() QuerySet methods:
            - .active() filters to only PENDING/OVERDUE invoices
            - .totals() aggregates billed amount and paid amount
            - Returns difference as outstanding balance
        
        Returns: Decimal - Amount user is owed by all clients combined
        
        Used By:
            - Dashboard top card showing "Total Outstanding"
            - User profile pages
            - Credit decisions and aging reports
        """
        # This now works because .active() and .totals() are on the QuerySet
        stats = self.filter(user=user).active().totals()
        return stats["billed"] - stats["paid"]

    def get_active_billed_total(self, user):
        """
        Calculates total billed amount for a user across all sent invoices.
        
        Business Logic: Billed = Total amount invoiced for SENT invoices
        
        Includes: PENDING, OVERDUE, PAID (all invoices actually sent to clients)
        Excludes: DRAFT (not sent), CANCELLED (invalid), and Quotes.
        
        Rationale: DRAFT invoices haven't been sent to clients yet, so they shouldn't
        count as "billed" in user-facing dashboards.
        
        Returns: Decimal - Total amount sent to clients (excluding DRAFT, CANCELLED)
        
        Used By:
            - Dashboard card "Total Billed" 
            - Financial reports
        """
        total = self.filter(user=user, is_quote=False).exclude(status__in=["DRAFT", "CANCELLED"]).aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]
        return total

    def get_dashboard_stats(self, user):
        """
        Gathers comprehensive invoice statistics for dashboard display.
        
        Summary Data: Returns dict with 4 key metrics:
        
        Returns:
            {
                'total_billed': Decimal - Sum of ALL invoice totals (includes DRAFT, PENDING, PAID, etc)
                'total_paid': Decimal - Sum of all payments received
                'total_outstanding': Decimal - total_billed minus total_paid  
                'invoice_count': int - Total number of invoices (excluding quotes)
            }
        
        Scope: ALL invoices (not filtered like get_total_outstanding which excludes DRAFT/PAID)
        because dashboard wants to show TOTAL revenue, not just "at risk" amounts.
        
        Used By:
            - Dashboard main stats cards
            - Financial overview pages
            - Revenue reporting
        """

    def get_tax_summary(self, user):
        """
        Calculates VAT liability summary tracking the complete VAT flow.
        
        VAT Flow for South African (SARS):
        1. Invoice POSTED (PENDING/OVERDUE) → Liability is SET (accrued)
        2. Invoice PAID by client → Liability is COLLECTED (cash received)
        3. Tax Payment recorded → Paid to SARS (duty settled)
        
        Calculations:
            - 'accrued': Total VAT from all POSTED invoices (PENDING, PAID, OVERDUE) = Tax liability owed
            - 'collected': VAT from PAID invoices only = Tax collected from clients (cash in)
            - 'paid': Total VAT remitted to SARS (from TaxPayment records) = Tax duty settled
            - 'outstanding': accrued - paid = Tax liability still owed to SARS
        
        Returns:
            {
                'accrued': Decimal - Total VAT liability SET when invoices posted
                'collected': Decimal - VAT received from clients (PAID invoices)
                'paid': Decimal - VAT remitted to SARS
                'outstanding': Decimal - VAT liable but not yet paid to SARS
            }
        
        Used By:
            - Tax dashboard/reporting
            - VAT reconciliation
            - Tax compliance tracking
            - Quarterly/annual tax submissions
        
        Data Sources:
            - Invoice.tax_amount from different statuses
            - TaxPayment.amount records where tax_type='VAT'
        """
        # Local import to prevent Circular Import error if TaxPayment is in models.py
        from .models import TaxPayment

        users_to_filter = [user]
        
        # 1. Total VAT liability ACCRUED (invoices posted but may not be paid yet)
        # This is VAT from all POSTED invoices: PENDING, PAID, OVERDUE
        accrued = self.filter(user__in=users_to_filter, status__in=["PENDING", "PAID", "OVERDUE"], is_quote=False).aggregate(
            res=Coalesce(Sum("tax_amount"), Decimal("0.00"))
        )["res"]

        # 2. VAT actually COLLECTED (money received from clients)
        # This is VAT from PAID invoices only (client has paid)
        collected = self.filter(user__in=users_to_filter, status="PAID", is_quote=False).aggregate(
            res=Coalesce(Sum("tax_amount"), Decimal("0.00"))
        )["res"]

        # 3. Total VAT already PAID to SARS
        paid = TaxPayment.objects.filter(user__in=users_to_filter, tax_type="VAT").aggregate(
            res=Coalesce(Sum("amount"), Decimal("0.00"))
        )["res"]

        return {
            "accrued": accrued,
            "collected": collected, 
            "paid": paid, 
            "outstanding": accrued - paid
        }

    def get_tax_year_dates(self, user=None):
        """
        Returns the start and end dates of the current tax year.
        Tax year depends on user's profile setting, defaults to South Africa (Mar 1 - Feb 28).
        """
        from dateutil.relativedelta import relativedelta
        
        today = timezone.now().date()
        
        # Get tax year type from user profile if provided
        tax_year_type = "ZA"  # default
        if user and hasattr(user, 'profile'):
            tax_year_type = getattr(user.profile, 'tax_year_type', 'ZA')
        
        # Tax year definitions by country (as month and day when tax year starts)
        tax_year_map = {
            "ZA": (3, 1),    # South Africa: March 1
            "US": (1, 1),    # USA: January 1
            "CA": (1, 1),    # Canada: January 1
            "UK": (4, 1),    # UK: April 1
            "AU": (7, 1),    # Australia: July 1
            "NZ": (4, 1),    # New Zealand: April 1
        }
        
        start_month, start_day = tax_year_map.get(tax_year_type, (3, 1))
        
        # Calculate start date of current tax year
        tax_year_start = date(today.year, start_month, start_day)
        
        # If we haven't reached the tax year start yet this year, use last year's
        if today < tax_year_start:
            tax_year_start = date(today.year - 1, start_month, start_day)
        
        # End date is one day before next year's start
        next_year_start = tax_year_start + relativedelta(years=1)
        tax_year_end = next_year_start - relativedelta(days=1)
        
        return tax_year_start, tax_year_end

    def get_tax_year_report(self, user):
        """Calculates total net revenue for the current income tax year (excluding quotes)."""
        start, end = self.get_tax_year_dates(user)
        users_to_filter = [user]
        res = self.filter(user__in=users_to_filter, date_issued__range=[start, end], is_quote=False).aggregate(
            net_revenue=Sum("subtotal_amount"), total_vat=Sum("tax_amount")
        )
        return {
            "start": start,
            "end": end,
            "net_revenue": res["net_revenue"] or Decimal("0.00"),
            "total_vat": res["total_vat"] or Decimal("0.00"),
        }

    def get_ytd_revenue(self, user):
        """
        Get year-to-date revenue for the current tax year.
        Returns total amount billed (excluding quotes and cancelled invoices).
        """
        report = self.get_tax_year_report(user)
        # Net revenue is subtotal; add VAT if registered to get full billed amount
        return report["net_revenue"] + report["total_vat"]

    def get_revenue_vs_target(self, user):
        """
        Compare YTD revenue against annual target.
        Returns dict with YTD revenue, target, remaining, and percentage complete.
        """
        ytd = self.get_ytd_revenue(user)
        profile = user.profile
        annual_target = profile.get_annual_revenue_target()
        
        # Calculate progress
        remaining = annual_target - ytd
        percent_complete = (ytd / annual_target * 100) if annual_target > 0 else 0
        
        # Pro-rata check: have we earned the expected amount for this day of the year?
        today = timezone.now().date()
        day_of_year = Decimal(str(today.timetuple().tm_yday))
        expected_by_today = annual_target * (day_of_year / Decimal("365.25"))
        on_track = ytd >= expected_by_today
        
        return {
            "ytd_revenue": ytd,
            "annual_target": annual_target,
            "remaining": remaining,
            "percent_complete": min(percent_complete, 100),  # Cap at 100%
            "on_track": on_track,
        }

    def check_vat_threshold(self, user):
        """
        Check if YTD revenue has crossed the VAT/GST registration threshold.
        Returns dict with threshold_crossed flag and details.
        """
        ytd = self.get_ytd_revenue(user)
        profile = user.profile
        threshold = profile.get_vat_thresholds()
        
        has_crossed = ytd >= threshold
        
        # Update profile flag
        if has_crossed and not profile.threshold_crossed:
            profile.threshold_crossed = True
            profile.save(update_fields=['threshold_crossed'])
        
        return {
            "threshold": threshold,
            "ytd_revenue": ytd,
            "crossed": has_crossed,
            "amount_over": max(0, ytd - threshold),
            "message": f"Revenue of {profile.currency}{ytd:,.2f} exceeds VAT threshold of {profile.currency}{threshold:,.2f}" if has_crossed else None,
        }

    def get_client_stats(self, client):
        """Get outstanding, payments, and totals for a single client."""
        qs = self.filter(client=client, is_quote=False)
        stats = qs.with_totals().aggregate(
            billed=Coalesce(Sum("total_amount"), Decimal("0.00")),
            paid=Coalesce(Sum("annotated_paid"), Decimal("0.00")),
        )
        return {
            "billed": stats["billed"],
            "paid": stats["paid"],
            "outstanding": stats["billed"] - stats["paid"],
        }

    def get_client_outstanding(self, client):
        """
        Calculates the outstanding balance owed BY a specific client.
        
        Business Context: Returns money THE CLIENT owes (unpaid invoices).
        Only counts PENDING and OVERDUE invoices (excludes DRAFT, CANCELLED, PAID).
        
        Calculation:
            - Sums total_amount from PENDING/OVERDUE invoices
            - Subtracts all payments already received
            - Result = current amount client still owes
        
        Parameters:
            client (Client): The client to calculate for
            
        Returns: Decimal - Outstanding balance (negative means client overpaid)
        
        Used By:
            - client_summary_detail.html Outstanding Balance card
            - clients/summary.py for ClientSummary object
            - Client payment tracking
            - Payment reminders/collections
        
        Query Filtering: Excludes DRAFT (not sent), CANCELLED (void), PAID (settled), and Quotes
        """
        stats = self.filter(client=client, status__in=["PENDING", "OVERDUE"], is_quote=False).with_totals().aggregate(
            billed=Coalesce(Sum("total_amount"), Decimal("0.00")),
            paid=Coalesce(Sum("annotated_paid"), Decimal("0.00")),
        )
        return stats["billed"] - stats["paid"]

    def get_user_stats(self, user):
        """
        Comprehensive invoice statistics for a user across all statuses.
        
        Scope: ALL invoices (DRAFT, PENDING, OVERDUE, PAID) EXCEPT CANCELLED.
        This shows TOTAL BUSINESS ACTIVITY, not just outstanding.
        
        Returns:
            {
                'billed': Decimal - Total amount invoiced across ALL statuses
                'paid': Decimal - Total amount paid (from PAID invoices)
                'outstanding': Decimal - Total still owed (billed - paid)
            }
        
        Used By:
            - User profile summary
            - Business performance analysis
            - Tax/accounting reports (total revenue)
            - Year-end financial reporting
        
        Excludes: CANCELLED invoices and Quotes (is_quote=False)
        """
        qs = self.filter(user=user, is_quote=False).exclude(status="CANCELLED")
        stats = qs.with_totals().aggregate(
            billed=Coalesce(Sum("total_amount"), Decimal("0.00")),
            paid=Coalesce(Sum("annotated_paid"), Decimal("0.00")),
        )
        return {
            "billed": stats["billed"],
            "paid": stats["paid"],
            "outstanding": stats["billed"] - stats["paid"],
        }

    def get_user_quote_total(self, user):
        """Get total value of quotes for a user (excludes CANCELLED)."""
        total = self.filter(user=user, is_quote=True).exclude(status="CANCELLED").aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]
        return total

    def get_client_total_billed(self, client):
        """Get total billed amount for a client (excludes DRAFT, CANCELLED, and quotes).
        
        "Total Billed" = All invoices actually sent to client + their payments.
        Includes: PENDING, OVERDUE, PAID (sent invoices with values)
        Excludes: DRAFT (not sent), CANCELLED (invalid), Quotes
        """
        total = self.filter(client=client, is_quote=False).exclude(status__in=["DRAFT", "CANCELLED"]).aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]
        return total

    def get_client_total_paid(self, client):
        """Get total paid amount for a client (excludes CANCELLED and quotes)."""
        qs = self.filter(client=client, is_quote=False).exclude(status="CANCELLED")
        stats = qs.with_totals().aggregate(
            paid=Coalesce(Sum("annotated_paid"), Decimal("0.00"))
        )
        return stats["paid"]

    def get_client_invoice_count(self, client):
        """Get invoice count for a client (excludes CANCELLED and quotes)."""
        return self.filter(client=client, is_quote=False).exclude(status="CANCELLED").count()

    def get_paid_invoices_total(self, user):
        """Get total revenue from PAID invoices for a user (excludes quotes)."""
        total = self.filter(user=user, status="PAID", is_quote=False).aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]
        return total

    def get_pending_invoices_total(self, user):
        """Get total from PENDING/OVERDUE invoices for a user (excludes quotes)."""
        total = self.filter(user=user, status__in=["PENDING", "OVERDUE"], is_quote=False).aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]
        return total

    def get_grand_total_billed(self, users=None):
        """Get grand total of all invoices (for admin/ops views). Pass None for all users."""
        qs = self.filter(is_quote=False).exclude(status="CANCELLED")
        if users:
            qs = qs.filter(user__in=users)
        total = qs.aggregate(total=Coalesce(Sum("total_amount"), Decimal("0.00")))["total"]
        return total

    def get_client_invoices_before_date(self, client, before_date):
        """
        Calculates total outstanding balance for invoices issued BEFORE a specific date.
        
        Use Case: Aging analysis - "how much from invoices over 30/60/90 days old?"
        
        Query Filters: 
            - date_issued < before_date
            - status IN (PENDING, OVERDUE)  [unpaid invoices only]
            - is_quote=False, status != CANCELLED
        
        Parameters:
            client (Client): The client to filter for
            before_date (date): Cutoff date (invoices BEFORE this are included)
            
        Returns: Decimal - Total outstanding from older invoices
        
        Used By:
            - Accounts receivable aging reports
            - Collection follow-up analysis
            - Invoice aging dashboard
        """
        total = self.filter(
            client=client, 
            date_issued__lt=before_date, 
            status__in=["PENDING", "OVERDUE"],
            is_quote=False
        ).aggregate(total=Coalesce(Sum("total_amount"), Decimal("0.00")))["total"]
        return total

    def get_client_invoices_after_date(self, client, after_date):
        """
        Calculates total billed amount for invoices issued ON OR AFTER a specific date.
        
        Use Case: Period-based reporting - "what was invoiced in this quarter/month?"
        
        Query Filters:
            - date_issued >= after_date
            - Excludes CANCELLED invoices
            - Excludes Quotes
            - All status types included (shows what was billed, not just unpaid)
        
        Parameters:
            client (Client): The client to filter for
            after_date (date): Start date (invoices from this date onward are included)
            
        Returns: Decimal - Total invoice amount (includes paid + unpaid)
        
        Used By:
            - Financial period reporting
            - Monthly/quarterly billing summaries
            - Client invoicing history tracking
        """
        total = self.filter(
            client=client, 
            date_issued__gte=after_date, 
            is_quote=False
        ).exclude(status="CANCELLED").aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]
        return total

    def get_client_invoices_in_range(self, client, start_date, end_date):
        """Get total billed for invoices in a date range."""
        total = self.filter(
            client=client, 
            date_issued__gte=start_date,
            date_issued__lt=end_date,
            is_quote=False
        ).exclude(status="CANCELLED").aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]
        return total


class PaymentManager(models.Manager):
    """
    Manager for Payment model - consolidates all payment-related calculations.
    
    Responsibilities:
    1. Calculating payments for invoices, clients, and users
    2. Tracking credit applied during payments
    3. Aggregating payment data for reporting
    """
    
    def get_invoice_total_paid(self, invoice):
        """
        Calculates total amount paid TOWARD a specific invoice.
        
        Scope: Sums all Payment.amount records linked to this invoice
        
        Parameters:
            invoice (Invoice): The invoice to calculate for
            
        Returns: Decimal - Total paid (0 if no payments)
        
        Used By:
            - InvoiceManager.update_totals() to calculate balance
            - Invoice detail pages to show payment history
            - Outstanding calculation (total_amount - paid = balance)
        """
        total = self.filter(invoice=invoice).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]
        return total
    
    def get_client_total_paid(self, client):
        """
        Calculates total amount paid BY a specific client across all their invoices.
        
        Scope: Sums all payments from all invoices for this client
        
        Parameters:
            client (Client): The client to calculate for
            
        Returns: Decimal - Total received from client (all-time, all invoices)
        
        Used By:
            - client_summary_detail.html Payments card
            - clients/summary.py for ClientSummary object
            - Client relationship analytics
        """
        total = self.filter(invoice__client=client).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]
        return total
    
    def get_user_total_received(self, user):
        """
        Calculates total revenue collected by a user from all invoices.
        
        Scope: Sums all payments from all invoices across all clients for this user
        
        Parameters:
            user (User): The user to calculate for
            
        Returns: Decimal - Total revenue received (all-time, all clients and invoices)
        
        Used By:
            - Dashboard Payments card showing revenue received
            - Financial summary and KPI tracking
            - Income statement line items
        """
        total = self.filter(invoice__user=user).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]
        return total
    
    def get_user_total_credit_applied(self, user):
        """Get total credit applied across all payments for a user."""
        total = self.filter(invoice__user=user).aggregate(
            total=Coalesce(Sum("credit_applied"), Decimal("0.00"))
        )["total"]
        return total

    def get_client_payments_before_date(self, client, before_date):
        """Get total payments for a client before a date."""
        total = self.filter(
            invoice__client=client,
            date_paid__lt=before_date
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
        return total

    def get_client_payments_after_date(self, client, after_date):
        """Get total payments for a client on or after a date."""
        total = self.filter(
            invoice__client=client,
            date_paid__gte=after_date
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
        return total

    def get_client_payments_in_range(self, client, start_date, end_date):
        """Get total payments for a client in a date range."""
        total = self.filter(
            invoice__client=client,
            date_paid__gte=start_date,
            date_paid__lt=end_date
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
        return total


class CreditNoteManager(models.Manager):
    """Manager for CreditNote model - consolidates all credit note calculations."""
    
    def get_client_credit_balance(self, client):
        """Get total available credit balance for a client."""
        total = self.filter(client=client).aggregate(
            total=Coalesce(Sum("balance"), Decimal("0.00"))
        )["total"]
        return total
    
    def get_client_credit_issued(self, client):
        """Get total amount of credit notes issued to a client."""
        total = self.filter(client=client).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]
        return total
    
    def get_user_total_credits_issued(self, user):
        """Get total credit notes issued by a user."""
        total = self.filter(client__user=user).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]
        return total
    
    def get_user_total_available_credit(self, user):
        """Get total available credit balance across all clients for a user."""
        total = self.filter(client__user=user).aggregate(
            total=Coalesce(Sum("balance"), Decimal("0.00"))
        )["total"]
        return total
    
    def get_client_credit_by_type(self, client):
        """Get credit notes breakdown by type for a client."""
        from django.db.models import CharField, Value
        return self.filter(client=client).values("note_type").annotate(
            total=Coalesce(Sum("amount"), Decimal("0.00")),
            available=Coalesce(Sum("balance"), Decimal("0.00"))
        )

    def get_client_credits_before_date(self, client, before_date):
        """Get total credits issued to a client before a date."""
        total = self.filter(
            client=client,
            issued_date__lt=before_date
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
        return total

    def get_client_credits_after_date(self, client, after_date):
        """Get total credits issued to a client on or after a date."""
        total = self.filter(
            client=client,
            issued_date__gte=after_date
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
        return total

    def get_client_credits_in_range(self, client, start_date, end_date):
        """Get total credits issued to a client in a date range."""
        total = self.filter(
            client=client,
            issued_date__gte=start_date,
            issued_date__lt=end_date
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
        return total
