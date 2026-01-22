from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.db.models import Sum, F, Q
from django.db.models.functions import Coalesce
from datetime import date
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
        """Recalculates and saves financial snapshots for DRAFT invoices."""
        if invoice.status != 'DRAFT':
            return

        profile = getattr(invoice.user, 'profile', None)
        is_registered = getattr(profile, 'is_vat_registered', False)
        
        # Using row_subtotal property from InvoiceItem
        items = invoice.items.all()
        subtotal = sum((item.row_subtotal for item in items), Decimal('0.00'))
        
        tax_amount = Decimal('0.00')
        if is_registered and invoice.tax_mode != 'NONE':
            rate = getattr(profile, 'vat_rate', Decimal('15.00')) / Decimal('100.00')
            
            if invoice.tax_mode == 'FULL':
                tax_amount = subtotal * rate
            elif invoice.tax_mode == 'MIXED':
                taxable_sum = sum((i.row_subtotal for i in items if i.is_taxable), Decimal('0.00'))
                tax_amount = taxable_sum * rate

        invoice.subtotal_amount = subtotal
        invoice.tax_amount = tax_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        invoice.total_amount = subtotal + invoice.tax_amount
        invoice.latex_content = "" 
        
        invoice.save(update_fields=['subtotal_amount', 'tax_amount', 'total_amount', 'latex_content'])

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