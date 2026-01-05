from decimal import Decimal
from collections import defaultdict
from datetime import timedelta

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, F, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from django.views.generic import ListView
from django.utils import timezone

# Internal App Imports
from .models import TimesheetEntry, WorkCategory
from .forms import TimesheetEntryForm
from clients.models import Client
from invoices.models import Invoice, InvoiceItem

# --- 1. LIST & DASHBOARD ---

@login_required
def get_category_fields(request):
    category_id = request.GET.get('category')
    if category_id:
        category = get_object_or_404(WorkCategory, id=category_id, user=request.user)
        # category.metadata_schema is your list like ['Attendees', 'Location']
        return render(request, 'timesheets/includes/category_fields.html', {
            'schema': category.metadata_schema
        })
    return HttpResponse("")  # Return nothing if "Standard Work" is selected
    


class TimesheetListView(LoginRequiredMixin, ListView):
    model = TimesheetEntry
    template_name = 'timesheets/timesheet_list.html'
    context_object_name = 'entries'

    def get_queryset(self):
        """Only show uninvoiced items in the main table view."""
        return TimesheetEntry.objects.filter(
            user=self.request.user, 
            is_billed=False
        ).order_by('-date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        
        start_of_week = today - timedelta(days=today.weekday())
        start_of_month = today.replace(day=1)

        # FETCH CATEGORIES FOR THE MODAL
        categories = WorkCategory.objects.filter(user=self.request.user).order_by('name')

        clients = Client.objects.filter(user=self.request.user).annotate(
            weekly_actual=Coalesce(
                Sum('timesheets__hours', filter=Q(timesheets__date__gte=start_of_week)), 
                Value(0, output_field=DecimalField())
            ),
            monthly_actual=Coalesce(
                Sum('timesheets__hours', filter=Q(timesheets__date__gte=start_of_month)), 
                Value(0, output_field=DecimalField())
            )
        ).order_by('name')

        client_stats = []
        for c in clients:
            client_stats.append({
                'client': c,
                'weekly_actual': c.weekly_actual,
                'weekly_target': c.weekly_target_hours,
                'weekly_percent': float((c.weekly_actual / c.weekly_target_hours * 100)) if c.weekly_target_hours > 0 else 0,
            })

        all_month_qs = TimesheetEntry.objects.filter(user=self.request.user, date__gte=start_of_month)
        totals = all_month_qs.aggregate(
            total_hours=Sum('hours'),
            total_value=Sum(F('hours') * F('hourly_rate'))
        )
        
        total_val = totals['total_value'] or Decimal('0.00')
        target_amount = Decimal('50000.00')

        context.update({
            'client_stats': client_stats,
            'clients': clients,
            'categories': categories,
            'total_hours': totals['total_hours'] or 0,
            'total_value': total_val,
            'target_amount': target_amount,
            'progress_percent': float(min((total_val / target_amount) * 100, 100)) if target_amount > 0 else 0,
            'timesheet_form': TimesheetEntryForm(),
        })
        return context

# --- 2. LOGGING, EDITING & DELETION ---


@login_required
def log_time(request):
    if request.method == 'POST':
        form = TimesheetEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            
            # 1. Fallback for rate if not provided
            if not entry.hourly_rate or entry.hourly_rate == 0:
                entry.hourly_rate = entry.client.default_hourly_rate

            # 2. Capture HTMX Dynamic Metadata
            # This loops through all POST data and grabs anything starting with 'meta_'
            meta_data = {}
            for key, value in request.POST.items():
                if key.startswith('meta_'):
                    field_name = key.replace('meta_', '')
                    if value.strip():  # Only save if not empty
                        meta_data[field_name] = value
            
            entry.metadata = meta_data
            entry.save()
            messages.success(request, f"Logged {entry.hours}h for {entry.client.name}.")
        else:
            messages.error(request, "Please correct the errors below.")
            # If form is invalid, we redirect back so the user can see error messages
    
    return redirect('timesheets:timesheet_list')



@login_required
def edit_entry(request, pk):
    entry = get_object_or_404(TimesheetEntry, pk=pk, user=request.user)


    if request.method == 'POST':
        form = TimesheetEntryForm(request.POST, instance=entry)
        if form.is_valid():
            entry = form.save(commit=False)
            
            # Re-capture metadata during edit
            meta_data = {}
            for key, value in request.POST.items():
                if key.startswith('meta_'):
                    meta_data[key.replace('meta_', '')] = value
            
            entry.metadata = meta_data
            entry.save()
            messages.success(request, "Entry updated.")
            return redirect('timesheets:timesheet_list')



    if entry.is_billed:
        messages.error(request, "Cannot edit invoiced entries.")
        return redirect('timesheets:timesheet_list')

    form = TimesheetEntryForm(request.POST or None, instance=entry)
    if request.method == 'POST' and form.is_valid():
        entry = form.save(commit=False)
        
        # Update metadata during edit
        meta_data = {}
        for key, value in request.POST.items():
            if key.startswith('meta_'):
                meta_data[key.replace('meta_', '')] = value
        
        entry.metadata = meta_data
        entry.save()
        messages.success(request, "Updated successfully.")
        return redirect('timesheets:timesheet_list')
    
    # Need categories here for the edit template dropdown
    categories = WorkCategory.objects.filter(user=request.user)
    return render(request, 'timesheets/edit_entry_form.html', {
        'form': form, 
        'entry': entry,
        'categories': categories
    })

@login_required
def delete_entry(request, pk):
    entry = get_object_or_404(TimesheetEntry, pk=pk, user=request.user)
    if entry.is_billed:
        messages.error(request, "Cannot delete invoiced entries.")
    else:
        entry.delete()
        messages.success(request, "Entry deleted.")
    return redirect('timesheets:timesheet_list')

# --- 3. CONSOLIDATED INVOICE GENERATOR ---

@login_required
def generate_invoice_bulk(request):
    if request.method != 'POST':
        return redirect('timesheets:timesheet_list')

    selected_ids = request.POST.getlist('selected_entries')
    if not selected_ids:
        messages.warning(request, "Select entries first.")
        return redirect('timesheets:timesheet_list')

    with transaction.atomic():
        entries = TimesheetEntry.objects.select_for_update().filter(
            id__in=selected_ids, user=request.user, is_billed=False
        ).select_related('client', 'category')

        if not entries.exists():
            return redirect('timesheets:timesheet_list')

        client_map = defaultdict(list)
        for entry in entries:
            client_map[entry.client].append(entry)

        for client, client_entries in client_map.items():
            invoice = Invoice.objects.create(
                user=request.user,
                client=client,
                due_date=timezone.now().date() + timedelta(days=client.payment_terms or 14)
            )

            # WE AGGREGATE BY: Description + Rate + Metadata
            # This ensures that specific meetings stay detailed
            line_items = defaultdict(Decimal) 
            for entry in client_entries:
                # We build a unique key that includes the specific detail
                detail_str = ""
                if entry.metadata:
                    detail_str = "\n" + "\n".join([f"{k}: {v}" for k, v in entry.metadata.items()])
                
                full_desc = f"{entry.description}{detail_str}"
                key = (full_desc, entry.hourly_rate)
                
                line_items[key] += entry.hours
                
                entry.is_billed = True
                entry.invoice = invoice
                entry.save()

            for (desc, rate), total_h in line_items.items():
                InvoiceItem.objects.create(
                    invoice=invoice, description=desc, quantity=total_h, unit_price=rate
                )

        messages.success(request, f"Generated {len(client_map)} invoice(s).")

    return redirect('invoices:invoice_list')