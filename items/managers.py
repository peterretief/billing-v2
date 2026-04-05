# items/managers.py

from django.utils import timezone as django_timezone

from django.utils import timezone

from django.db import models
from django.db.models import F, Sum
from core.managers import TenantManager


class ItemManager(TenantManager):

    def queued_for_billing(self, user):
        """Recurring items not yet billed this month."""
        current_month_start = timezone.now().date().replace(day=1)
        return self.filter(
            user=user,
            is_recurring=True,
        ).exclude(last_billed_date__gte=current_month_start)

    def unbilled(self, user):
        return self.filter(user=user, invoice__isnull=True)

    def total_unbilled_value(self, user, client=None):
        queryset = self.unbilled(user)
        if client:
            queryset = queryset.filter(client=client)

        result = queryset.aggregate(total=Sum(F("quantity") * F("unit_price")))
        return result["total"] or 0

    def can_be_invoiced(self, item_ids):
        """
        Validates whether selected items are eligible to be invoiced.

        Business Rule: Items can only be invoiced once. Once an item is linked to an invoice 
        (via the invoice foreign key), it becomes "processed" and cannot be invoiced again.

        Parameters:
            item_ids (list): List of Item IDs to validate

        Returns:
            tuple: (can_invoice: bool, count_already_invoiced: int)
                - can_invoice: True if ALL items are unprocessed (invoice_id is NULL)
                - count_already_invoiced: Number of items already linked to invoices

        Used By:
            - items/views.py: CreateInvoiceFromItemsView (line 119)
            - Invoice creation form validation to prevent double-invoicing

        Query: Counts items with invoice__isnull=False (already processed)
        """
        already_invoiced = self.filter(id__in=item_ids, invoice__isnull=False).count()
        return already_invoiced == 0, already_invoiced

    def get_unprocessed(self, user, client=None):
        """
        Retrieves all unprocessed items for a user (optionally filtered by client).

        Business Context: "Unprocessed" items are items not yet linked to any invoice.
        These are items that are ready to be invoiced or currently pending invoicing.

        Parameters:
            user (User): The user who owns the items
            client (Client, optional): If provided, filters to only this client's items

        Returns:
            QuerySet: Filtered Item objects where invoice_id is NULL

        Used By:
            - clients/summary.py: ClientSummary.get_items() - for progress bar calculations
            - Displays unprocessed item counts and values on client detail pages

        Query: Filters on user and invoice__isnull=True
        """
        queryset = self.filter(user=user, invoice__isnull=True)
        if client:
            queryset = queryset.filter(client=client)
        return queryset

    def get_unprocessed_value(self, user, client=None):
        """
        Calculates the total monetary value of unprocessed items.

        Calculation: Sum of (quantity * unit_price) for all unprocessed items.

        Parameters:
            user (User): The user who owns the items
            client (Client, optional): If provided, limits calculation to this client

        Returns:
            Decimal: Total value in currency (Decimal type for financial accuracy)
                Returns 0 if no unprocessed items exist

        Used By:
            - clients/summary.py: ClientSummary.get_items() - for value-based progress percentages
            - clients_summary_dashboard.html: AllClientsSummary aggregates all clients' unprocessed values
            - Dashboard displays total unprocessed item value across all clients

        Query: Calls get_unprocessed() then aggregates with Sum(quantity * unit_price)
        """
        queryset = self.get_unprocessed(user, client)
        result = queryset.aggregate(total=Sum(F("quantity") * F("unit_price")))
        return result["total"] or 0