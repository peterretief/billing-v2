from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


class InvoiceQuerySet(models.QuerySet):
    def active(self):
        """Filters for invoices that are issued/unpaid."""
        return self.exclude(status__in=['DRAFT', 'PAID', 'CANCELLED'])

    def totals(self):
        """
        Returns aggregated financial stats.
        Note: We use 'distinct=True' on payments to avoid inflating totals 
        due to the JOIN between InvoiceItems and Payments.
        """
        return self.aggregate(
            billed=Coalesce(Sum('total_amount'), Decimal('0.00')),
            tax=Coalesce(Sum('tax_amount'), Decimal('0.00')),
            # distinct=True is critical here if you have multiple payments per invoice
            paid=Coalesce(Sum('payments__amount', distinct=True), Decimal('0.00')),
        )

class InvoiceManager(models.Manager.from_queryset(InvoiceQuerySet)):

    def update_totals(self, invoice):
        if invoice.status != 'DRAFT':
            return

        profile = getattr(invoice.user, 'profile', None)
        is_registered = getattr(profile, 'is_vat_registered', False)
    
        subtotal = Decimal('0.00')
    
        # --- LOGIC GATE START ---
    
        # 1. Primary Source: Billed Items
        has_items = False
        if hasattr(invoice, 'billed_items') and invoice.billed_items.exists():
            items = invoice.billed_items.all()
            subtotal += sum((item.quantity * item.unit_price for item in items), Decimal('0.00'))
            has_items = True
    
        # 2. Fallback Source: Timesheets
        # ONLY add timesheets if NO items were found.
        if not has_items and hasattr(invoice, 'billed_timesheets'):
            timesheets = invoice.billed_timesheets.all()
            subtotal += sum((ts.hours * ts.hourly_rate for ts in timesheets), Decimal('0.00'))

        # 3. Custom Items
        # (If you want custom lines to ALWAYS add, keep this separate)
        if hasattr(invoice, 'custom_lines'):
            subtotal += sum((line.total for line in invoice.custom_lines.all()), Decimal('0.00'))
    
        # --- LOGIC GATE END ---

        # 4. Tax Calculation
        tax_amount = Decimal('0.00')
        if is_registered and invoice.tax_mode != 'NONE':
            rate_val = getattr(profile, 'vat_rate', Decimal('15.00'))
            rate = rate_val / Decimal('100.00')
            tax_amount = subtotal * rate

        invoice.subtotal_amount = subtotal
        invoice.tax_amount = tax_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        invoice.total_amount = subtotal + invoice.tax_amount
    
        invoice.save(update_fields=['subtotal_amount', 'tax_amount', 'total_amount'])


    def get_total_outstanding(self, user):
        stats = self.filter(user=user).active().totals()
        return stats['billed'] - stats['paid']

    def get_dashboard_stats(self, user):
        qs = self.filter(user=user)
        stats = qs.totals()
        
        return {
            'total_billed': stats['billed'],
            'total_tax': stats['tax'],
            'total_paid': stats['paid'],
            'total_outstanding': stats['billed'] - stats['paid'],
            'invoice_count': qs.count(),
        }
    
    def get_tax_summary(self, user):
        """Calculates VAT collected vs VAT paid to SARS."""
        # Local import to prevent Circular Import error if TaxPayment is in models.py
        from .models import TaxPayment

        # 1. Total VAT collected from customers (Only from PAID invoices)
        collected = self.filter(user=user, status='PAID').aggregate(
            res=Coalesce(Sum('tax_amount'), Decimal('0.00'))
        )['res']

       # 2. Total VAT already paid to SARS
        paid = TaxPayment.objects.filter(user=user, tax_type='VAT').aggregate(
            res=Coalesce(Sum('amount'), Decimal('0.00'))
        )['res']

        return {
            'collected': collected,
            'paid': paid,
            'outstanding': collected - paid
        }
    
    def get_tax_year_dates(self):
        """Returns the start and end dates of the current SA Tax Year."""
        today = timezone.now().date()
        # SA Tax year starts March 1st
        if today.month >= 3:
            start_date = date(today.year, 3, 1)
            end_date = date(today.year + 1, 2, 28)
        else:
            start_date = date(today.year - 1, 3, 1)
            end_date = date(today.year, 2, 28)
        return start_date, end_date

    def get_tax_year_report(self, user):
        """Calculates total net revenue for the current income tax year."""
        start, end = self.get_tax_year_dates()
        res = self.filter(user=user, date_issued__range=[start, end]).aggregate(
            net_revenue=Sum('subtotal_amount'),
            total_vat=Sum('tax_amount')
        )
        return {
            'start': start,
            'end': end,
            'net_revenue': res['net_revenue'] or Decimal('0.00'),
            'total_vat': res['total_vat'] or Decimal('0.00'),
        }