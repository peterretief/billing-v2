"""
Utilities for generating reconciliation statements.
"""
from decimal import Decimal
from datetime import date
from django.db.models import Sum, DecimalField, F, Value
from django.db.models.functions import Coalesce

from invoices.models import Invoice, Payment, CreditNote
from clients.models import Client


class ClientReconciliation:
    """
    Generate reconciliation data for a single client.
    Shows balance movements: opening → invoices → payments → closing with summary and details.
    """
    
    def __init__(self, client, user, start_date=None, end_date=None):
        self.client = client
        self.user = user
        self.start_date = start_date
        self.end_date = end_date or date.today()
        
    def get_opening_balance(self):
        """
        Calculate opening balance before start_date.
        For simplicity, assume all invoices before period are settled or this is first period.
        """
        if not self.start_date:
            return Decimal('0.00')
        
        # Sum all invoices issued before start_date that are not fully paid
        before_period = Invoice.objects.filter(
            user=self.user,
            client=self.client,
            date_issued__lt=self.start_date,
            status__in=['PENDING', 'OVERDUE']
        ).aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0.00'))
        )['total']
        
        # Subtract payments before start_date
        payments_before = Payment.objects.filter(
            user=self.user,
            invoice__client=self.client,
            date_paid__lt=self.start_date
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00'))
        )['total']
        
        # Subtract credit notes used before start_date
        credits_used = CreditNote.objects.filter(
            user=self.user,
            client=self.client,
            issued_date__lt=self.start_date
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00'))
        )['total']
        
        return before_period - payments_before - credits_used
    
    def get_transactions(self):
        """
        Get all transactions in chronological order within period.
        Returns list of dicts with type, description, amount, running_balance
        """
        transactions = []
        running_balance = self.get_opening_balance()
        
        # Get all invoices in period
        invoices = Invoice.objects.filter(
            user=self.user,
            client=self.client,
            date_issued__gte=self.start_date,
            date_issued__lte=self.end_date
        ).exclude(status='DRAFT').order_by('date_issued')
        
        for invoice in invoices:
            # Only show non-draft invoices in recon
            if invoice.status != 'DRAFT':
                running_balance += invoice.total_amount
                
                # Show cancelled invoices specially
                if invoice.status == 'CANCELLED':
                    transactions.append({
                        'type': 'INVOICE_CANCELLED',
                        'date': invoice.date_issued,
                        'description': f'Invoice {invoice.number} Cancelled - {invoice.cancellation_reason or "No reason provided"}',
                        'amount': -invoice.total_amount,  # Negative as reversal
                        'running_balance': running_balance,
                        'invoice': invoice,
                        'detail': f'Was: {invoice.total_amount}'
                    })
                else:
                    transactions.append({
                        'type': 'INVOICE',
                        'date': invoice.date_issued,
                        'description': f'Invoice {invoice.number}',
                        'amount': invoice.total_amount,
                        'running_balance': running_balance,
                        'invoice': invoice,
                        'detail': f'Due: {invoice.due_date}'
                    })
        
        # Get all payments in period
        payments = Payment.objects.filter(
            user=self.user,
            invoice__client=self.client,
            date_paid__gte=self.start_date,
            date_paid__lte=self.end_date
        ).order_by('date_paid').select_related('invoice')
        
        for payment in payments:
            running_balance -= payment.amount
            transactions.append({
                'type': 'PAYMENT',
                'date': payment.date_paid,
                'description': f'Payment received - Invoice {payment.invoice.number}',
                'amount': -payment.amount,
                'running_balance': running_balance,
                'payment': payment,
                'detail': f'Ref: {payment.reference or "N/A"}'
            })
        
        # Get all credit notes in period
        credit_notes = CreditNote.objects.filter(
            user=self.user,
            client=self.client,
            issued_date__gte=self.start_date,
            issued_date__lte=self.end_date
        ).order_by('issued_date')
        
        for credit in credit_notes:
            running_balance -= credit.amount
            transactions.append({
                'type': 'CREDIT_NOTE',
                'date': credit.issued_date,
                'description': f'Credit Note {credit.reference or "CN"}',
                'amount': -credit.amount,
                'running_balance': running_balance,
                'credit_note': credit,
                'detail': f'{credit.get_note_type_display()}: {credit.description}'
            })
        
        # Sort all transactions by date
        transactions.sort(key=lambda x: x['date'])
        
        return transactions
    
    def get_summary(self):
        """Get summary statistics for the period."""
        transactions = self.get_transactions()
        
        invoices_sent = Invoice.objects.filter(
            user=self.user,
            client=self.client,
            date_issued__gte=self.start_date,
            date_issued__lte=self.end_date,
            status__in=['PENDING', 'PAID', 'OVERDUE']
        ).aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
        
        invoices_cancelled = Invoice.objects.filter(
            user=self.user,
            client=self.client,
            date_issued__gte=self.start_date,
            date_issued__lte=self.end_date,
            status='CANCELLED'
        ).aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
        
        payments_received = Payment.objects.filter(
            user=self.user,
            invoice__client=self.client,
            date_paid__gte=self.start_date,
            date_paid__lte=self.end_date
        ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']
        
        credit_notes_issued = CreditNote.objects.filter(
            user=self.user,
            client=self.client,
            issued_date__gte=self.start_date,
            issued_date__lte=self.end_date
        ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']
        
        opening_balance = self.get_opening_balance()
        closing_balance = opening_balance + invoices_sent - invoices_cancelled - payments_received - credit_notes_issued
        
        return {
            'opening_balance': opening_balance,
            'invoices_sent': invoices_sent,
            'invoices_cancelled': invoices_cancelled,
            'payments_received': payments_received,
            'credit_notes_issued': credit_notes_issued,
            'closing_balance': closing_balance,
            'transaction_count': len(transactions),
        }
    
    def get_cancelled_invoices_sent(self):
        """Get all cancelled invoices that were sent (not just drafted then cancelled)."""
        return Invoice.objects.filter(
            user=self.user,
            client=self.client,
            status='CANCELLED',
            is_emailed=True  # Was actually sent before cancellation
        ).order_by('-date_issued')
    
    def get_outstanding_credit(self):
        """Get total outstanding credit available for this client."""
        return CreditNote.objects.filter(
            user=self.user,
            client=self.client
        ).aggregate(
            total=Coalesce(Sum('balance'), Decimal('0.00'))
        )['total']
    
    def get_full_report(self):
        """Get complete reconciliation report."""
        return {
            'client': self.client,
            'period_start': self.start_date,
            'period_end': self.end_date,
            'summary': self.get_summary(),
            'transactions': self.get_transactions(),
            'cancelled_sent': self.get_cancelled_invoices_sent(),
            'outstanding_credit': self.get_outstanding_credit(),
        }


class AllClientsReconciliation:
    """
    Generate reconciliation summary for all clients.
    Each client gets a summary row showing outstanding balance, credits, etc.
    """
    
    def __init__(self, user, end_date=None):
        self.user = user
        self.end_date = end_date or date.today()
    
    def get_all_clients_summary(self):
        """
        Get summary row for each client.
        """
        clients = Client.objects.filter(user=self.user).order_by('name')
        summaries = []
        
        for client in clients:
            # Outstanding invoices
            outstanding = Invoice.objects.filter(
                user=self.user,
                client=client,
                status__in=['PENDING', 'OVERDUE']
            ).aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.00')))['total']
            
            # Total payments
            payments_total = Payment.objects.filter(
                user=self.user,
                invoice__client=client
            ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']
            
            # Credit balance
            credit_balance = CreditNote.objects.filter(
                user=self.user,
                client=client
            ).aggregate(total=Coalesce(Sum('balance'), Decimal('0.00')))['total']
            
            # Cancelled sent invoices
            cancelled_sent = Invoice.objects.filter(
                user=self.user,
                client=client,
                status='CANCELLED',
                is_emailed=True
            ).count()
            
            # All invoices count
            all_invoices = Invoice.objects.filter(
                user=self.user,
                client=client
            ).exclude(status='DRAFT').count()
            
            summaries.append({
                'client': client,
                'outstanding_balance': outstanding,
                'total_payments': payments_total,
                'credit_balance': credit_balance,
                'cancelled_sent_count': cancelled_sent,
                'total_invoices': all_invoices,
                'net_position': outstanding - payments_total,  # What client owes vs what already paid
            })
        
        return summaries
