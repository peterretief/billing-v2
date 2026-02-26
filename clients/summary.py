"""
Client summary utility for comprehensive client reporting.
Provides methods to gather quotes, timesheets, items, invoices, and other metrics by client.
"""

from decimal import Decimal
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import Coalesce

from invoices.models import Invoice, CreditNote, Payment
from timesheets.models import TimesheetEntry
from items.models import Item


class ClientSummary:
    """
    Gathers comprehensive summary data for a single client.
    Includes quotes, timesheets, items, invoices, and various metrics.
    """

    def __init__(self, client):
        self.client = client

    def get_quotes(self):
        """Get quote summary: counts and totals by status."""
        quotes = self.client.invoices.filter(is_quote=True)
        
        return {
            "pending": {
                "count": quotes.filter(quote_status="PENDING").count(),
                "total": quotes.filter(quote_status="PENDING").aggregate(
                    total=Coalesce(Sum("total_amount"), Decimal("0.00"))
                )["total"],
            },
            "accepted": {
                "count": quotes.filter(quote_status="ACCEPTED").count(),
                "total": quotes.filter(quote_status="ACCEPTED").aggregate(
                    total=Coalesce(Sum("total_amount"), Decimal("0.00"))
                )["total"],
            },
            "rejected": {
                "count": quotes.filter(quote_status="REJECTED").count(),
                "total": quotes.filter(quote_status="REJECTED").aggregate(
                    total=Coalesce(Sum("total_amount"), Decimal("0.00"))
                )["total"],
            },
            "total_count": quotes.count(),
            "total_value": quotes.aggregate(total=Coalesce(Sum("total_amount"), Decimal("0.00")))["total"],
        }

    def get_timesheets(self):
        """Get timesheet summary: processed (invoiced) vs unprocessed."""
        timesheets = TimesheetEntry.objects.filter(client=self.client)
        processed_timesheets = timesheets.filter(invoice__isnull=False)
        unprocessed_timesheets = timesheets.filter(invoice__isnull=True)

        # Calculate totals by iterating through records
        processed_total = Decimal("0.00")
        for ts in processed_timesheets:
            processed_total += ts.hours * ts.hourly_rate

        unprocessed_total = Decimal("0.00")
        for ts in unprocessed_timesheets:
            unprocessed_total += ts.hours * ts.hourly_rate

        all_total = Decimal("0.00")
        for ts in timesheets:
            all_total += ts.hours * ts.hourly_rate

        total_count = timesheets.count()
        processed_count = processed_timesheets.count()
        processed_pct = (processed_count * 100) // total_count if total_count > 0 else 0
        
        # Calculate value-based percentage
        processed_value_pct = int((processed_total * 100) / all_total) if all_total > 0 else 0

        return {
            "processed": {
                "count": processed_count,
                "hours": processed_timesheets.aggregate(
                    total=Coalesce(Sum("hours"), Decimal("0.00"))
                )["total"],
                "total": processed_total,
            },
            "unprocessed": {
                "count": unprocessed_timesheets.count(),
                "hours": unprocessed_timesheets.aggregate(
                    total=Coalesce(Sum("hours"), Decimal("0.00"))
                )["total"],
                "total": unprocessed_total,
            },
            "total_count": total_count,
            "total_hours": timesheets.aggregate(total=Coalesce(Sum("hours"), Decimal("0.00")))["total"],
            "total_value": all_total,
            "processed_pct": processed_pct,
            "processed_value_pct": processed_value_pct,
        }

    def get_items(self):
        """Get item summary: processed (invoiced) vs unprocessed."""
        items = Item.objects.filter(client=self.client)
        processed_items = items.filter(invoice__isnull=False)
        unprocessed_items = items.filter(invoice__isnull=True)

        # Calculate totals by iterating through records
        processed_total = Decimal("0.00")
        for item in processed_items:
            processed_total += item.quantity * item.unit_price

        unprocessed_total = Decimal("0.00")
        for item in unprocessed_items:
            unprocessed_total += item.quantity * item.unit_price

        all_total = Decimal("0.00")
        for item in items:
            all_total += item.quantity * item.unit_price

        total_count = items.count()
        processed_count = processed_items.count()
        processed_pct = (processed_count * 100) // total_count if total_count > 0 else 0
        
        # Calculate value-based percentage
        processed_value_pct = int((processed_total * 100) / all_total) if all_total > 0 else 0

        return {
            "processed": {
                "count": processed_count,
                "total": processed_total,
            },
            "unprocessed": {
                "count": unprocessed_items.count(),
                "total": unprocessed_total,
            },
            "total_count": total_count,
            "total_value": all_total,
            "processed_pct": processed_pct,
            "processed_value_pct": processed_value_pct,
        }

    def get_invoices(self):
        """Get invoice summary: by status (excluding quotes)."""
        invoices = self.client.invoices.filter(is_quote=False)

        statuses = ["DRAFT", "PENDING", "OVERDUE", "PAID", "CANCELLED"]
        result = {}

        for status in statuses:
            status_invoices = invoices.filter(status=status)
            result[status.lower()] = {
                "count": status_invoices.count(),
                "total": status_invoices.aggregate(
                    total=Coalesce(Sum("total_amount"), Decimal("0.00"))
                )["total"],
            }

        result["total_count"] = invoices.count()
        result["total_value"] = invoices.aggregate(
            total=Coalesce(Sum("total_amount"), Decimal("0.00"))
        )["total"]

        return result

    def get_email_status(self):
        """Get email status: emailed vs not emailed (invoices only, not quotes)."""
        invoices = self.client.invoices.filter(is_quote=False)

        return {
            "emailed": {
                "count": invoices.filter(is_emailed=True).count(),
                "total": invoices.filter(is_emailed=True).aggregate(
                    total=Coalesce(Sum("total_amount"), Decimal("0.00"))
                )["total"],
            },
            "not_emailed": {
                "count": invoices.filter(is_emailed=False).count(),
                "total": invoices.filter(is_emailed=False).aggregate(
                    total=Coalesce(Sum("total_amount"), Decimal("0.00"))
                )["total"],
            },
        }

    def get_outstanding(self):
        """Get outstanding balance: unpaid PENDING/OVERDUE invoices using manager."""
        from invoices.models import Invoice
        
        outstanding_amount = Invoice.objects.get_client_outstanding(self.client)
        
        # Ensure outstanding_amount is never None (convert to Decimal 0)
        if outstanding_amount is None:
            outstanding_amount = Decimal("0.00")
        
        # Get count of outstanding invoices
        outstanding_count = Invoice.objects.filter(
            client=self.client,
            is_quote=False,
            status__in=["PENDING", "OVERDUE"]
        ).count()

        return {
            "count": outstanding_count,
            "total": outstanding_amount,
        }

    def get_credit_notes(self):
        """Get credit notes summary: by type.
        
        Uses 'balance' (available credit) to align with reconciliation reports.
        """
        credits = CreditNote.objects.filter(client=self.client)

        credit_types = [choice[0] for choice in CreditNote.NoteType.choices]
        result = {}

        for credit_type in credit_types:
            type_credits = credits.filter(note_type=credit_type)
            result[credit_type.lower()] = {
                "count": type_credits.count(),
                "total": type_credits.aggregate(
                    total=Coalesce(Sum("balance"), Decimal("0.00"))
                )["total"],
            }

        result["total_count"] = credits.count()
        result["total_value"] = credits.aggregate(
            total=Coalesce(Sum("balance"), Decimal("0.00"))
        )["total"]

        return result

    def get_payments(self):
        """Get total payments received from client."""
        payments = Payment.objects.filter(invoice__client=self.client)
        total_payments = payments.aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]
        
        return {
            "count": payments.count(),
            "total": total_payments,
        }

    def get_summary(self):
        """Get complete summary for client."""
        outstanding = self.get_outstanding()
        credit_notes = self.get_credit_notes()
        
        # Calculate net position: outstanding - credit
        # Safely handle None values by converting to Decimal 0
        outstanding_total = outstanding.get("total") or Decimal("0.00")
        credit_total = credit_notes.get("total_value") or Decimal("0.00")
        net_position = outstanding_total - credit_total
        
        return {
            "client": self.client,
            "quotes": self.get_quotes(),
            "timesheets": self.get_timesheets(),
            "items": self.get_items(),
            "invoices": self.get_invoices(),
            "email_status": self.get_email_status(),
            "payments": self.get_payments(),
            "outstanding": outstanding,
            "credit_notes": credit_notes,
            "net_position": net_position,
        }


class AllClientsSummary:
    """
    Aggregates summary data for all clients.
    Useful for dashboard-level reporting.
    """

    def __init__(self, user):
        self.user = user

    def get_all_summaries(self):
        """Get summary for all clients for this user."""
        from clients.models import Client

        clients = Client.objects.filter(user=self.user).order_by("name")
        summaries = []

        for client in clients:
            summary = ClientSummary(client).get_summary()
            summaries.append(summary)

        return summaries

    def get_totals(self):
        """Get aggregated totals across all clients."""
        summaries = self.get_all_summaries()

        totals = {
            "clients_count": len(summaries),
            "quotes_total_count": sum(s["quotes"]["total_count"] for s in summaries),
            "quotes_total_value": sum(s["quotes"]["total_value"] for s in summaries),
            "timesheets_total_count": sum(s["timesheets"]["total_count"] for s in summaries),
            "timesheets_total_hours": sum(s["timesheets"]["total_hours"] for s in summaries),
            "timesheets_total_value": sum(s["timesheets"]["total_value"] for s in summaries),
            "timesheets_processed_count": sum(s["timesheets"]["processed"]["count"] for s in summaries),
            "timesheets_processed_value": sum(s["timesheets"]["processed"]["total"] for s in summaries),
            "timesheets_unprocessed_count": sum(s["timesheets"]["unprocessed"]["count"] for s in summaries),
            "timesheets_unprocessed_value": sum(s["timesheets"]["unprocessed"]["total"] for s in summaries),
            "items_total_count": sum(s["items"]["total_count"] for s in summaries),
            "items_total_value": sum(s["items"]["total_value"] for s in summaries),
            "items_processed_count": sum(s["items"]["processed"]["count"] for s in summaries),
            "items_processed_value": sum(s["items"]["processed"]["total"] for s in summaries),
            "items_unprocessed_count": sum(s["items"]["unprocessed"]["count"] for s in summaries),
            "items_unprocessed_value": sum(s["items"]["unprocessed"]["total"] for s in summaries),
            "invoices_total_count": sum(s["invoices"]["total_count"] for s in summaries),
            "invoices_total_value": sum(s["invoices"]["total_value"] for s in summaries),
            "payments_total_count": sum(s["payments"]["count"] for s in summaries),
            "payments_total_value": sum(s["payments"]["total"] for s in summaries),
        }
        
        # Calculate totals for outstanding and credit
        outstanding_total = sum(s["outstanding"]["total"] for s in summaries)
        credit_notes_total_count = sum(s["credit_notes"]["total_count"] for s in summaries)
        credit_notes_total_value = sum(s["credit_notes"]["total_value"] for s in summaries)
        
        totals.update({
            "outstanding_total": outstanding_total,
            "credit_notes_total_count": credit_notes_total_count,
            "credit_notes_total_value": credit_notes_total_value,
            "net_position_total": outstanding_total - credit_notes_total_value,
        })

        return totals
