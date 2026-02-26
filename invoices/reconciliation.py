"""
Utilities for generating reconciliation statements.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from clients.models import Client
from invoices.models import CreditNote, Invoice, Payment


class ReconciliationVerification:
    """
    Verifies reconciliation calculations using dual methods.
    Every total is calculated two different ways and compared.
    """

    def __init__(self):
        self.errors = []
        self.warnings = []

    def verify_calculation(self, name, method1_result, method1_name, method2_result, method2_name):
        """
        Compare two calculation methods for the same value.
        Raises error if they don't match.
        """
        if method1_result != method2_result:
            msg = (
                f"RECONCILIATION MISMATCH: {name}\n"
                f"  {method1_name}: {method1_result}\n"
                f"  {method2_name}: {method2_result}\n"
                f"  Difference: {abs(method1_result - method2_result)}"
            )
            self.errors.append(msg)
            return False
        return True

    def add_warning(self, msg):
        """Track a warning."""
        self.warnings.append(msg)

    def has_errors(self):
        """Check if verification found errors."""
        return len(self.errors) > 0

    def get_report(self):
        """Get verification report."""
        return {"errors": self.errors, "warnings": self.warnings}


class ClientReconciliation:
    """
    Generate reconciliation data for a single client.
    Shows balance movements: opening → invoices → payments → closing with summary and details.
    
    DUAL VERIFICATION: Every calculation is done with 2 methods and compared.
    """

    def __init__(self, client, user, start_date=None, end_date=None):
        self.client = client
        self.user = user
        self.start_date = start_date
        self.end_date = end_date or date.today()
        self.verifier = ReconciliationVerification()

    def get_opening_balance(self):
        """
        Calculate opening balance before start_date using TWO methods.
        Method 1: ORM aggregation (via managers)
        Method 2: Iterate and sum
        """
        if not self.start_date:
            return Decimal("0.00")

        # METHOD 1: ORM Aggregation using manager methods (centralized calculations)
        before_period_1 = Invoice.objects.get_client_invoices_before_date(self.client, self.start_date)
        payments_before_1 = Payment.objects.get_client_payments_before_date(self.client, self.start_date)
        credits_used_1 = CreditNote.objects.get_client_credits_before_date(self.client, self.start_date)

        method1_result = before_period_1 - payments_before_1 - credits_used_1

        # METHOD 2: Iterate and sum manually (for verification)
        before_period_2 = Decimal("0.00")
        for inv in Invoice.objects.filter(
            user=self.user, client=self.client, date_issued__lt=self.start_date, 
            status__in=["PENDING", "OVERDUE"], is_quote=False
        ):
            before_period_2 += inv.total_amount

        payments_before_2 = Decimal("0.00")
        for pmt in Payment.objects.filter(
            user=self.user, invoice__client=self.client, date_paid__lt=self.start_date
        ):
            payments_before_2 += pmt.amount

        credits_used_2 = Decimal("0.00")
        for credit in CreditNote.objects.filter(
            user=self.user, client=self.client, issued_date__lt=self.start_date
        ):
            credits_used_2 += credit.amount

        method2_result = before_period_2 - payments_before_2 - credits_used_2

        # VERIFY both methods match
        self.verifier.verify_calculation(
            "Opening Balance",
            method1_result,
            "ORM Aggregation (Manager)",
            method2_result,
            "Manual Iteration"
        )

        return method1_result

    def get_transactions(self):
        """
        Get all transactions in chronological order within period.
        Returns list of dicts with type, description, amount, running_balance
        """
        transactions = []
        running_balance = self.get_opening_balance()

        # Build invoice filter
        invoice_filter = {"user": self.user, "client": self.client, "date_issued__lte": self.end_date}
        if self.start_date:
            invoice_filter["date_issued__gte"] = self.start_date

        # Get all invoices in period (excluding quotes and drafts)
        invoices = Invoice.objects.filter(**invoice_filter).exclude(status="DRAFT", is_quote=True).order_by("date_issued")

        for invoice in invoices:
            # Only show non-draft invoices in recon
            if invoice.status != "DRAFT":
                running_balance += invoice.total_amount

                # Show cancelled invoices specially
                if invoice.status == "CANCELLED":
                    transactions.append(
                        {
                            "type": "INVOICE_CANCELLED",
                            "date": invoice.date_issued,
                            "description": f"Invoice {invoice.number} Cancelled - {invoice.cancellation_reason or 'No reason provided'}",
                            "amount": -invoice.total_amount,  # Negative as reversal
                            "running_balance": running_balance,
                            "invoice": invoice,
                            "detail": f"Was: {invoice.total_amount}",
                        }
                    )
                else:
                    transactions.append(
                        {
                            "type": "INVOICE",
                            "date": invoice.date_issued,
                            "description": f"Invoice {invoice.number}",
                            "amount": invoice.total_amount,
                            "running_balance": running_balance,
                            "invoice": invoice,
                            "detail": f"Due: {invoice.due_date}",
                        }
                    )

        # Get all payments in period
        payment_filter = {"user": self.user, "invoice__client": self.client, "date_paid__lte": self.end_date}
        if self.start_date:
            payment_filter["date_paid__gte"] = self.start_date

        payments = Payment.objects.filter(**payment_filter).order_by("date_paid").select_related("invoice")

        for payment in payments:
            payment_total = payment.amount + payment.credit_applied
            running_balance -= payment_total

            # Build detail string showing cash and credit breakdown
            detail_parts = [f"Ref: {payment.reference or 'N/A'}"]
            if payment.amount > 0 and payment.credit_applied > 0:
                detail_parts.append(f"({payment.amount} cash + {payment.credit_applied} credit)")
            elif payment.credit_applied > 0:
                detail_parts.append(f"(Credit only: {payment.credit_applied})")

            transactions.append(
                {
                    "type": "PAYMENT",
                    "date": payment.date_paid,
                    "description": f"Payment received - Invoice {payment.invoice.number}",
                    "amount": -payment_total,
                    "running_balance": running_balance,
                    "payment": payment,
                    "detail": " ".join(detail_parts),
                }
            )

        # Get all credit notes in period
        credit_filter = {"user": self.user, "client": self.client, "issued_date__lte": self.end_date}
        if self.start_date:
            credit_filter["issued_date__gte"] = self.start_date

        credits = CreditNote.objects.filter(**credit_filter).order_by("issued_date")

        for credit in credits:
            running_balance -= credit.amount
            transactions.append(
                {
                    "type": "CREDIT_NOTE",
                    "date": credit.issued_date,
                    "description": f"Credit Note {credit.reference or 'CN'}",
                    "amount": -credit.amount,
                    "running_balance": running_balance,
                    "credit_note": credit,
                    "detail": f"{credit.get_note_type_display()}: {credit.description}",
                }
            )

        # Sort all transactions by date
        transactions.sort(key=lambda x: x["date"])

        return transactions

    def get_summary(self):
        """Get summary statistics for the period using DUAL VERIFICATION."""
        transactions = self.get_transactions()

        # Build filters
        invoice_filter = {
            "user": self.user,
            "client": self.client,
            "date_issued__lte": self.end_date,
            "status__in": ["PENDING", "PAID", "OVERDUE"],
            "is_quote": False,
        }
        if self.start_date:
            invoice_filter["date_issued__gte"] = self.start_date

        # INVOICES SENT - Method 1: ORM Aggregation
        invoices_sent_1 = Invoice.objects.filter(**invoice_filter).aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]

        # INVOICES SENT - Method 2: Manual iteration
        invoices_sent_2 = Decimal("0.00")
        for inv in Invoice.objects.filter(**invoice_filter):
            invoices_sent_2 += inv.total_amount

        # Verify invoices sent
        self.verifier.verify_calculation(
            "Invoices Sent (Period)",
            invoices_sent_1,
            "ORM Aggregation",
            invoices_sent_2,
            "Manual Iteration"
        )

        # CANCELLED INVOICES - Method 1: ORM Aggregation
        cancelled_filter = {
            "user": self.user,
            "client": self.client,
            "date_issued__lte": self.end_date,
            "status": "CANCELLED",
            "is_quote": False,
        }
        if self.start_date:
            cancelled_filter["date_issued__gte"] = self.start_date

        invoices_cancelled_1 = Invoice.objects.filter(**cancelled_filter).aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]

        # CANCELLED INVOICES - Method 2: Manual iteration
        invoices_cancelled_2 = Decimal("0.00")
        for inv in Invoice.objects.filter(**cancelled_filter):
            invoices_cancelled_2 += inv.total_amount

        # Verify invoices cancelled
        self.verifier.verify_calculation(
            "Invoices Cancelled (Period)",
            invoices_cancelled_1,
            "ORM Aggregation",
            invoices_cancelled_2,
            "Manual Iteration"
        )

        # PAYMENTS RECEIVED - Method 1: ORM Aggregation
        payment_filter = {"user": self.user, "invoice__client": self.client, "date_paid__lte": self.end_date}
        if self.start_date:
            payment_filter["date_paid__gte"] = self.start_date

        payments_received_1 = Payment.objects.filter(**payment_filter).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]

        # PAYMENTS RECEIVED - Method 2: Manual iteration
        payments_received_2 = Decimal("0.00")
        for pmt in Payment.objects.filter(**payment_filter):
            payments_received_2 += pmt.amount

        # Verify payments received
        self.verifier.verify_calculation(
            "Payments Received - Cash (Period)",
            payments_received_1,
            "ORM Aggregation",
            payments_received_2,
            "Manual Iteration"
        )

        # CREDIT APPLIED - Method 1: ORM Aggregation
        credit_in_payments_1 = Payment.objects.filter(**payment_filter).aggregate(
            total=Coalesce(Sum("credit_applied"), Decimal("0.00"))
        )["total"]

        # CREDIT APPLIED - Method 2: Manual iteration
        credit_in_payments_2 = Decimal("0.00")
        for pmt in Payment.objects.filter(**payment_filter):
            credit_in_payments_2 += pmt.credit_applied

        # Verify credit applied
        self.verifier.verify_calculation(
            "Credit Applied to Invoices (Period)",
            credit_in_payments_1,
            "ORM Aggregation",
            credit_in_payments_2,
            "Manual Iteration"
        )

        # CREDIT NOTES ISSUED - Method 1: ORM Aggregation
        credit_filter = {"user": self.user, "client": self.client, "issued_date__lte": self.end_date}
        if self.start_date:
            credit_filter["issued_date__gte"] = self.start_date

        credit_notes_issued_1 = CreditNote.objects.filter(**credit_filter).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]

        # CREDIT NOTES ISSUED - Method 2: Manual iteration
        credit_notes_issued_2 = Decimal("0.00")
        for credit in CreditNote.objects.filter(**credit_filter):
            credit_notes_issued_2 += credit.amount

        # Verify credit notes issued
        self.verifier.verify_calculation(
            "Credit Notes Issued (Period)",
            credit_notes_issued_1,
            "ORM Aggregation",
            credit_notes_issued_2,
            "Manual Iteration"
        )

        opening_balance = self.get_opening_balance()

        # CLOSING BALANCE - Method 1: Formula
        closing_balance_1 = (
            opening_balance + invoices_sent_1 - invoices_cancelled_1 
            - payments_received_1 - credit_in_payments_1 - credit_notes_issued_1
        )

        # CLOSING BALANCE - Method 2: Verify by walking through transactions
        closing_balance_2 = opening_balance
        for trans in transactions:
            closing_balance_2 += trans["amount"]

        # Verify closing balance matches via both methods
        self.verifier.verify_calculation(
            "Closing Balance",
            closing_balance_1,
            "Formula Method",
            closing_balance_2,
            "Transaction Walk-Through"
        )

        return {
            "opening_balance": opening_balance,
            "invoices_sent": invoices_sent_1,
            "invoices_cancelled": invoices_cancelled_1,
            "payments_received": payments_received_1,
            "credit_in_payments": credit_in_payments_1,
            "credit_notes_issued": credit_notes_issued_1,
            "closing_balance": closing_balance_1,
            "transaction_count": len(transactions),
            "verification_errors": self.verifier.errors,
            "verification_warnings": self.verifier.warnings,
        }

    def get_cancelled_invoices_sent(self):
        """Get all cancelled invoices (not quotes) that were sent (not just drafted then cancelled)."""
        return Invoice.objects.filter(
            user=self.user,
            client=self.client,
            status="CANCELLED",
            is_emailed=True,  # Was actually sent before cancellation
            is_quote=False,  # Only actual invoices, not quotes
        ).order_by("-date_issued")

    def get_full_report(self):
        """Get complete reconciliation report including verification data."""
        summary = self.get_summary()
        return {
            "client": self.client,
            "period_start": self.start_date,
            "period_end": self.end_date,
            "summary": summary,
            "transactions": self.get_transactions(),
            "cancelled_sent": self.get_cancelled_invoices_sent(),
            "outstanding_credit": CreditNote.objects.get_client_credit_balance(self.client),
            "verification_errors": summary.get("verification_errors", []),
            "verification_warnings": summary.get("verification_warnings", []),
            "has_verification_errors": len(summary.get("verification_errors", [])) > 0,
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
        Get summary row for each client using Invoice manager for outstanding calculation.
        """
        clients = Client.objects.filter(user=self.user).order_by("name")
        summaries = []

        for client in clients:
            # Use manager methods for all calculations (single source of truth)
            outstanding = Invoice.objects.get_client_outstanding(client)
            payments_total = Payment.objects.get_client_total_paid(client)
            credit_balance = CreditNote.objects.get_client_credit_balance(client)

            # Cancelled sent invoices (excluding quotes)
            cancelled_sent = Invoice.objects.filter(
                user=self.user, client=client, status="CANCELLED", is_emailed=True, is_quote=False
            ).count()

            # All invoices count (excluding quotes and drafts)
            all_invoices = Invoice.objects.filter(user=self.user, client=client, is_quote=False).exclude(status="DRAFT").count()

            summaries.append(
                {
                    "client": client,
                    "outstanding_balance": outstanding,
                    "total_payments": payments_total,
                    "credit_balance": credit_balance,
                    "cancelled_sent_count": cancelled_sent,
                    "total_invoices": all_invoices,
                    "net_position": outstanding - credit_balance,  # What client owes after applying available credit
                }
            )

        return summaries
