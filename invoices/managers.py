
from django.db import models
from decimal import Decimal

class InvoiceManager(models.Manager):
    def get_dashboard_stats(self, user):
        """
        Calculates grouped totals for the user dashboard.
        """
        # Get all user invoices at once to avoid multiple DB hits
        invoices = list(self.filter(user=user))
        
        stats = {
            'grand_total': Decimal('0.00'),
            'total_taxable_subtotal': Decimal('0.00'),
            'total_vat': Decimal('0.00'),
            'total_exempt_subtotal': Decimal('0.00'),
            'unpaid_total': Decimal('0.00'),
            'count': len(invoices)
        }

        for inv in invoices:
            # Accumulate the different buckets using the model properties
            stats['total_taxable_subtotal'] += inv.taxable_subtotal
            stats['total_vat'] += inv.vat_amount
            stats['total_exempt_subtotal'] += inv.non_taxable_subtotal
            stats['grand_total'] += inv.total_amount

            # Track unpaid amounts
            if inv.status in ['DRAFT', 'SENT', 'PENDING']:
                stats['unpaid_total'] += inv.total_amount

        return stats