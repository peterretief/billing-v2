from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum, Q  # Make sure Q is imported



class InvoiceManager(models.Manager):
    def update_totals(self, invoice):
        """Calculates and saves all totals for an invoice."""
        items = invoice.items.all()
        subtotal = sum((item.row_subtotal for item in items), Decimal('0.00'))
        
        # Determine Taxable Base
        if invoice.tax_mode == 'NONE': # EXEMPT
            tax_amount = Decimal('0.00')
        else:
            tax_rate = Decimal('0.15') # Or fetch from user profile
            if invoice.tax_mode == 'FULL':
                tax_amount = subtotal * tax_rate
            else: # MIXED
                taxable_sum = sum((i.row_subtotal for i in items if i.is_taxable), Decimal('0.00'))
                tax_amount = taxable_sum * tax_rate

        invoice.subtotal_amount = subtotal
        invoice.tax_amount = tax_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        invoice.total_amount = subtotal + invoice.tax_amount
        invoice.save(update_fields=['subtotal_amount', 'tax_amount', 'total_amount'])

    def get_dashboard_stats(self, user):
        qs = self.filter(user=user)
    
        # Helper for rounding
        def clean_decimal(value):
            if value is None:
                return Decimal('0.00')
            return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Use Q objects for filtering inside aggregate
        res = qs.aggregate(
            total=Sum('total_amount'),
            unpaid=Sum('total_amount', filter=Q(status__iexact='sent')),
            paid=Sum('total_amount', filter=Q(status__iexact='paid'))
        )

        return {
            'total_invoiced': clean_decimal(res['total']),
            'unpaid_amount': clean_decimal(res['unpaid']),
            'paid_amount': clean_decimal(res['paid']),
            'invoice_count': qs.count(),
        }