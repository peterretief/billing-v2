import profile
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.db.models import DecimalField, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


class InvoiceQuerySet(models.QuerySet):
    def with_totals(self):
        from .models import Payment
        # Subquery to sum payments for each invoice
        pay_sub = Payment.objects.filter(invoice=OuterRef('pk')).values('invoice')\
                         .annotate(total=Sum('amount')).values('total')
        
        return self.annotate(
            annotated_paid=Coalesce(Subquery(pay_sub, output_field=DecimalField()), Decimal('0.00'))
        )

    def active(self):
        # Exclude Drafts so they don't show up in 'Outstanding' math
        return self.exclude(status__in=['DRAFT', 'CANCELLED', 'PAID'])

    def totals(self):
        # This is what the Dashboard Cards use
        return self.with_totals().aggregate(
            billed=Coalesce(Sum('total_amount'), Decimal('0.00')),
            paid=Coalesce(Sum('annotated_paid'), Decimal('0.00')),
        )
    
class InvoiceManager(models.Manager.from_queryset(InvoiceQuerySet)):

    def update_totals(self, invoice):
        # Guard: only block CANCELLED, not PAID — we need to reach PAID from PENDING
        if invoice.status == 'CANCELLED':
            return

        #profile = getattr(invoice.user, 'profile', None)
        is_registered = getattr(profile, 'is_vat_registered', False)
        custom_vat_rate = getattr(profile, 'vat_rate', None) or Decimal('15.00')

        subtotal = Decimal('0.00')

        # A. Primary Source: Billed Items
        has_items = False
        if hasattr(invoice, 'billed_items') and invoice.billed_items.exists():
            items = invoice.billed_items.all()
            subtotal += sum((item.quantity * item.unit_price for item in items), Decimal('0.00'))
            has_items = True

        # B. Fallback Source: Timesheets
        if not has_items and hasattr(invoice, 'billed_timesheets'):
            timesheets = invoice.billed_timesheets.all()
            subtotal += sum((ts.hours * ts.hourly_rate for ts in timesheets), Decimal('0.00'))

        # C. Custom Items
        if hasattr(invoice, 'custom_lines'):
            subtotal += sum((line.total for line in invoice.custom_lines.all()), Decimal('0.00'))

        # Tax Calculation
        tax_amount = Decimal('0.00')
        if is_registered and invoice.tax_mode != 'NONE':
            rate = custom_vat_rate / Decimal('100.00')
            tax_amount = subtotal * rate

        invoice.subtotal_amount = subtotal
        invoice.tax_amount = tax_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        invoice.total_amount = subtotal + invoice.tax_amount

        # Status Sync — calculate balance directly from DB payments
        # to avoid stale in-memory values
        from django.db.models import Sum
        total_paid = invoice.payments.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00'))
        )['total']

        balance = invoice.total_amount - total_paid

        if invoice.status == 'PENDING' and balance <= 0:
            invoice.status = 'PAID'

        invoice.save(update_fields=[
            'subtotal_amount',
            'tax_amount',
            'total_amount',
            'status'
        ])

    def get_total_outstanding(self, user):
        # This now works because .active() and .totals() are on the QuerySet
        stats = self.filter(user=user).active().totals()
        return stats['billed'] - stats['paid']

    def get_dashboard_stats(self, user):
        qs = self.filter(user=user)
        stats = qs.totals()
        return {
            'total_billed': stats['billed'],
            'total_paid': stats['paid'],
            'total_outstanding': stats['billed'] - stats['paid'],
            'invoice_count': qs.count(),
        }

    
    def get_tax_summary(self, user):
        """Calculates VAT collected vs VAT paid to SARS."""
        # Local import to prevent Circular Import error if TaxPayment is in models.py
        from .models import TaxPayment

        users_to_filter = [user]
        if user.is_ops:
            users_to_filter.extend(list(user.added_users.all()))
        # 1. Total VAT collected from customers (Only from PAID invoices)
        collected = self.filter(user__in=users_to_filter, status='PAID').aggregate(
            res=Coalesce(Sum('tax_amount'), Decimal('0.00'))
        )['res']

       # 2. Total VAT already paid to SARS
        paid = TaxPayment.objects.filter(user__in=users_to_filter, tax_type='VAT').aggregate(
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
        users_to_filter = [user]
        if user.is_ops:
            users_to_filter.extend(list(user.added_users.all()))
        res = self.filter(user__in=users_to_filter, date_issued__range=[start, end]).aggregate(
            net_revenue=Sum('subtotal_amount'),
            total_vat=Sum('tax_amount')
        )
        return {
            'start': start,
            'end': end,
            'net_revenue': res['net_revenue'] or Decimal('0.00'),
            'total_vat': res['total_vat'] or Decimal('0.00'),
        }