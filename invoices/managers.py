from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum, Q

class InvoiceManager(models.Manager):
    def update_totals(self, invoice):
        """
        Calculates and saves all totals. 
        Protects 'Locked' invoices from accidental changes.
        """
        # 1. Safety Guard: Prevent changing totals on Sent/Paid invoices
        if invoice.status != 'DRAFT':
            return

        items = invoice.items.all()
        subtotal = sum((item.row_subtotal for item in items), Decimal('0.00'))
        
        # 2. Dynamic Tax Rate Logic
        if invoice.tax_mode == 'NONE':
            tax_amount = Decimal('0.00')
        else:
            # Fetch from UserProfile; fallback to 15% if profile missing
            profile = getattr(invoice.user, 'userprofile', None)
            raw_rate = profile.tax_rate if profile else Decimal('15.00')
            tax_rate = raw_rate / Decimal('100.00') 

            if invoice.tax_mode == 'FULL':
                tax_amount = subtotal * tax_rate
            else: # MIXED mode
                taxable_sum = sum((i.row_subtotal for i in items if i.is_taxable), Decimal('0.00'))
                tax_amount = taxable_sum * tax_rate

        # 3. Rounding and Saving
        invoice.subtotal_amount = subtotal
        invoice.tax_amount = tax_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        invoice.total_amount = subtotal + invoice.tax_amount
        
        # Clear LaTeX cache so the PDF regenerates with new math
        invoice.latex_content = "" 
        
        invoice.save(update_fields=['subtotal_amount', 'tax_amount', 'total_amount', 'latex_content'])

    def get_dashboard_stats(self, user):
        """
        Provides high-level aggregates for the dashboard.
        """
        qs = self.filter(user=user)
    
        def clean_decimal(value):
            if value is None:
                return Decimal('0.00')
            return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # 4. Aggregate Math (Database side)
        res = qs.aggregate(
            total=Sum('total_amount'),
            # Include Drafts, Pending, and Overdue in 'Unpaid'
            unpaid=Sum('total_amount', filter=Q(status__in=['DRAFT', 'PENDING', 'OVERDUE'])),
            paid=Sum('total_amount', filter=Q(status='PAID'))
        )

        return {
            'total_invoiced': clean_decimal(res['total']),
            'unpaid_amount': clean_decimal(res['unpaid']),
            'paid_amount': clean_decimal(res['paid']),
            'invoice_count': qs.count(),
        }