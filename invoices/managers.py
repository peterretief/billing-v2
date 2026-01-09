from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum, Q


class InvoiceManager__(models.Manager):
    def get_total_outstanding(self, user):
        """
        Calculates the actual debt owed to the tenant.
        Sum of (Total Invoice) - Sum of (Payments) for all issued invoices.
        """
        # 1. Grab invoices that are NOT Drafts, NOT Paid, and NOT Cancelled
        # This automatically includes 'SENT', 'POSTED', 'OVERDUE', etc.
        active_invoices = self.filter(user=user).exclude(
            status__in=['DRAFT', 'PAID', 'CANCELLED']
        )
        
        # 2. Sum up the 'total_amount' on those invoices
        total_billed = active_invoices.aggregate(
            res=models.Sum('total_amount')
        )['res'] or Decimal('0.00')
        
        # 3. Import Payment locally to avoid circular imports
        from .models import Payment 
        
        # 4. Sum up all payments linked to those active invoices
        total_paid = Payment.objects.filter(
            invoice__in=active_invoices
        ).aggregate(
            res=models.Sum('amount')
        )['res'] or Decimal('0.00')
        
        # 5. Return the net difference
        return total_billed - total_paid



class InvoiceManager(models.Manager):
    def get_total_outstanding(self, user):
        """
        Calculates the actual debt owed to the tenant.
        Sum of (Total Invoice) - Sum of (Payments) for all issued invoices.
        """
        # 1. Grab invoices that are NOT Drafts, NOT Paid, and NOT Cancelled
        # This automatically includes 'SENT', 'POSTED', 'OVERDUE', etc.
        active_invoices = self.filter(user=user).exclude(
            status__in=['DRAFT', 'PAID', 'CANCELLED']
        )
        
        # 2. Sum up the 'total_amount' on those invoices
        total_billed = active_invoices.aggregate(
            res=models.Sum('total_amount')
        )['res'] or Decimal('0.00')
        
        # 3. Import Payment locally to avoid circular imports
        from .models import Payment 
        
        # 4. Sum up all payments linked to those active invoices
        total_paid = Payment.objects.filter(
            invoice__in=active_invoices
        ).aggregate(
            res=models.Sum('amount')
        )['res'] or Decimal('0.00')
        
        # 5. Return the net difference
        return total_billed - total_paid



    def update_totals(self, invoice):
        if invoice.status != 'DRAFT':
            return

        items = invoice.items.all()
        subtotal = sum((item.row_subtotal for item in items), Decimal('0.00'))
        
        if invoice.tax_mode == 'NONE':
            tax_amount = Decimal('0.00')
        else:
            profile = getattr(invoice.user, 'userprofile', None)
            # Match your model's field name (vat_rate vs tax_rate)
            raw_rate = getattr(profile, 'vat_rate', Decimal('15.00'))
            tax_rate = raw_rate / Decimal('100.00') 

            if invoice.tax_mode == 'FULL':
                tax_amount = subtotal * tax_rate
            else: 
                taxable_sum = sum((i.row_subtotal for i in items if i.is_taxable), Decimal('0.00'))
                tax_amount = taxable_sum * tax_rate

        invoice.subtotal_amount = subtotal
        invoice.tax_amount = tax_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        invoice.total_amount = subtotal + invoice.tax_amount
        invoice.latex_content = "" 
        
        invoice.save(update_fields=['subtotal_amount', 'tax_amount', 'total_amount', 'latex_content'])

    def get_dashboard_stats(self, user):
        qs = self.filter(user=user)
    
        def clean_decimal(value):
            return Decimal(value or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Use the relationship to Payments to get real-time 'Paid' data
        res = qs.aggregate(
            total_billed=Sum('total_amount'),
            total_tax=Sum('tax_amount'),
            # Joins the Payment table to see actual cash received
            total_paid=Sum('payments__amount') 
        )

        billed = clean_decimal(res['total_billed'])
        paid = clean_decimal(res['total_paid'])
        tax = clean_decimal(res['total_tax'])

        return {
            'total_billed': billed,
            'total_tax': tax,
            'total_paid': paid,
            'total_outstanding': billed - paid, # The 'True' unpaid balance
            'invoice_count': qs.count(),
        }