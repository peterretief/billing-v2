from decimal import Decimal
from collections import defaultdict
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, F
from django.views.generic import ListView
from django.utils import timezone

# Internal App Imports
from .models import TimesheetEntry
from .forms import TimesheetEntryForm
from clients.models import Client
from invoices.models import Invoice, InvoiceItem

@login_required
def edit_entry(request, pk):
    entry = get_object_or_404(TimesheetEntry, pk=pk, user=request.user)
    
    if entry.is_billed:
        messages.error(request, "Cannot edit an entry that has already been invoiced.")
        return redirect('timesheets:timesheet_list')

    # Initialize the form with the existing data
    form = TimesheetEntryForm(request.POST or None, instance=entry)

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Entry updated successfully.")
            return redirect('timesheets:timesheet_list')
    
    # If it's a GET request (or form is invalid), show the edit page
    return render(request, 'timesheets/edit_entry_form.html', {
        'form': form, 
        'entry': entry
    })


# --- 1. LIST & DASHBOARD ---

class TimesheetListView(LoginRequiredMixin, ListView):
    model = TimesheetEntry
    template_name = 'timesheets/timesheet_list.html'
    context_object_name = 'entries'

    def get_queryset(self):
        """Only show work that hasn't been invoiced yet."""
        return TimesheetEntry.objects.filter(
            user=self.request.user, 
            is_billed=False  # This hides the 'Invoiced' items
        ).order_by('-date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        
        # Aggregation for the progress bar and cards
        totals = qs.aggregate(
            total_hours=Sum('hours'),
            total_value=Sum(F('hours') * F('hourly_rate'))
        )
        
        target_amount = Decimal('50000.00')
        total_value = totals['total_value'] or Decimal('0.00')
        
        context.update({
            'total_hours': totals['total_hours'] or 0,
            'total_value': total_value,
            'target_amount': target_amount,
            'progress_percent': float(min((total_value / target_amount) * 100, 100)) if target_amount > 0 else 0,
            'timesheet_form': TimesheetEntryForm(),
        })
        return context

# --- 2. LOGGING & DELETION ---

@login_required
def log_time(request):
    if request.method == 'POST':
        form = TimesheetEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, f"Logged {entry.hours} hours for {entry.client.name}.")
    return redirect(request.META.get('HTTP_REFERER', 'timesheets:timesheet_list'))

@login_required
def delete_entry(request, pk):
    entry = get_object_or_404(TimesheetEntry, pk=pk, user=request.user)
    if entry.is_billed:
        messages.error(request, "Cannot delete an entry that has already been invoiced.")
    else:
        entry.delete()
        messages.success(request, "Entry removed.")
    return redirect(request.META.get('HTTP_REFERER', 'timesheets:timesheet_list'))

# --- 3. THE INVOICE GENERATOR (BULK & CONSOLIDATED) ---

@login_required
def generate_invoice_bulk(request):
    if request.method != 'POST':
        return redirect('timesheets:timesheet_list')

    selected_ids = request.POST.getlist('selected_entries')
    if not selected_ids:
        messages.warning(request, "No entries selected.")
        return redirect(request.META.get('HTTP_REFERER', 'timesheets:timesheet_list'))

    with transaction.atomic():
        entries = TimesheetEntry.objects.select_for_update().filter(
            id__in=selected_ids,
            user=request.user,
            is_billed=False
        ).select_related('client')

        if not entries.exists():
            messages.warning(request, "No valid uninvoiced entries found.")
            return redirect(request.META.get('HTTP_REFERER', 'timesheets:timesheet_list'))

        # Step 1: Group by Client
        client_map = defaultdict(list)
        for entry in entries:
            client_map[entry.client].append(entry)

        invoices_created = 0
        today = timezone.now().date()

        for client, client_entries in client_map.items():
            days_to_add = getattr(client, 'payment_terms', 14) or 14
            due_date = today + timedelta(days=days_to_add)

            invoice = Invoice.objects.create(
                user=request.user,
                client=client,
                status='DRAFT',
                due_date=due_date
            )

            # Step 2: Group entries for THIS client by (Description + Rate)
            # We use a tuple (description, rate) as the key
            grouped_items = defaultdict(Decimal) 
            
            for entry in client_entries:
                key = (entry.description, entry.hourly_rate)
                grouped_items[key] += entry.hours
                
                # Still link the original entry to the invoice for audit trails
                entry.is_billed = True
                entry.invoice = invoice
                entry.save()

            # Step 3: Create the consolidated Line Items
            for (description, rate), total_hours in grouped_items.items():
                InvoiceItem.objects.create(
                    invoice=invoice,
                    description=description,
                    quantity=total_hours,
                    unit_price=rate
                )
            
            invoices_created += 1

        messages.success(request, f"Successfully created {invoices_created} consolidated invoice(s).")

    return redirect('invoices:invoice_list')