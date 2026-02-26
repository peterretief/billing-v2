# timesheets/managers.py
from django.db import models
from django.db.models import F, Sum


class TimesheetManager(models.Manager):
    def unbilled(self, user):
        return self.filter(user=user, is_billed=False)

    def total_unbilled_value(self, user, client=None):
        queryset = self.unbilled(user)
        if client:
            queryset = queryset.filter(client=client)

        # Calculation happens at the database level for speed
        result = queryset.aggregate(total=Sum(F("hours") * F("hourly_rate")))
        return result["total"] or 0
    
    def can_be_invoiced(self, entry_ids):
        """
        Validates whether selected timesheets are eligible to be invoiced.
        
        Business Rule: Timesheets can only be invoiced once. Once a timesheet entry is linked 
        to an invoice (via the invoice foreign key), it becomes "processed" and cannot be invoiced again.
        
        Parameters:
            entry_ids (list): List of TimesheetEntry IDs to validate
            
        Returns:
            tuple: (can_invoice: bool, count_already_invoiced: int)
                - can_invoice: True if ALL timesheet entries are unprocessed (invoice_id is NULL)
                - count_already_invoiced: Number of entries already linked to invoices
                
        Used By:
            - timesheets/views.py: CreateInvoiceFromTimesheetsView (line 391)
            - Invoice creation form validation to prevent double-invoicing
            
        Query: Counts entries with invoice__isnull=False (already processed)
        """
        already_invoiced = self.filter(id__in=entry_ids, invoice__isnull=False).count()
        return already_invoiced == 0, already_invoiced

    def get_unprocessed(self, user, client=None):
        """
        Retrieves all unprocessed timesheet entries for a user (optionally filtered by client).
        
        Business Context: "Unprocessed" timesheet entries are entries not yet linked to any invoice.
        These are entries that are ready to be invoiced or currently pending invoicing.
        
        Parameters:
            user (User): The user who owns the timesheet entries
            client (Client, optional): If provided, filters to only this client's entries
            
        Returns:
            QuerySet: Filtered TimesheetEntry objects where invoice_id is NULL
            
        Used By:
            - clients/summary.py: ClientSummary.get_timesheets() - for progress bar calculations
            - Displays unprocessed timesheet counts and values on client detail pages
            
        Query: Filters on user and invoice__isnull=True
        """
        queryset = self.filter(user=user, invoice__isnull=True)
        if client:
            queryset = queryset.filter(client=client)
        return queryset

    def get_unprocessed_value(self, user, client=None):
        """
        Calculates the total monetary value of unprocessed timesheet entries.
        
        Calculation: Sum of (hours * hourly_rate) for all unprocessed entries.
        
        Parameters:
            user (User): The user who owns the timesheet entries
            client (Client, optional): If provided, limits calculation to this client
            
        Returns:
            Decimal: Total value in currency (Decimal type for financial accuracy)
                Returns 0 if no unprocessed entries exist
                
        Used By:
            - clients/summary.py: ClientSummary.get_timesheets() - for value-based progress percentages
            - clients_summary_dashboard.html: AllClientsSummary aggregates all clients' unprocessed timesheet values
            - Dashboard displays total unprocessed timesheet value across all clients
            
        Query: Calls get_unprocessed() then aggregates with Sum(hours * hourly_rate)
        """
        queryset = self.get_unprocessed(user, client)
        result = queryset.aggregate(total=Sum(F("hours") * F("hourly_rate")))
        return result["total"] or 0