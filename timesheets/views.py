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
from .forms import TimesheetEntryForm,WorkCategoryForm
from clients.models import Client
from invoices.models import Invoice, InvoiceItem

# --- 1. LIST & DASHBOARD ---

import subprocess
import os
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.conf import settings


from collections import defaultdict

@login_required
def export_metadata_pdf(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
    # Fetch entries linked to this invoice
    entries = TimesheetEntry.objects.filter(invoice=invoice).select_related('category').order_by('date')
    
    # Group by Category Name
    grouped_entries = defaultdict(list)
    for entry in entries:
        cat_name = entry.category.name if entry.category else "General"
        grouped_entries[cat_name].append(entry)

    context = {
        'invoice_number': invoice.number,
        'client_name': invoice.client.name,
        'date_generated': timezone.now().strftime('%d %b %Y'),
        'grouped_data': dict(grouped_entries), # Pass the dictionary
        'total_hours': sum(e.hours for e in entries),
    }


    # 1. Render the LaTeX string
    tex_content = render_to_string('timesheets/reports/metadata_report.tex', context)
    
    # 2. Save to temporary file and compile
    temp_dir = os.path.join(settings.BASE_DIR, 'tmp')
    if not os.path.exists(temp_dir): os.makedirs(temp_dir)
    
    tex_file_path = os.path.join(temp_dir, f'report_{invoice.id}.tex')
    with open(tex_file_path, 'w') as f:
        f.write(tex_content)

    # Run pdflatex (ensure pdflatex is installed on your server)
    subprocess.run(['pdflatex', '-output-directory', temp_dir, tex_file_path])

    # 3. Return the PDF
    pdf_path = tex_file_path.replace('.tex', '.pdf')
    with open(pdf_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Work_Log_{invoice.number}.pdf"'
        return response

@login_required
def manage_categories(request):
    # Fetch all categories belonging to the user
    categories = WorkCategory.objects.filter(user=request.user).order_by('name')
    
    if request.method == 'POST':
        form = WorkCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, f"Category '{category.name}' created successfully!")
            return redirect('timesheets:manage_categories')
    else:
        form = WorkCategoryForm()

    return render(request, 'timesheets/manage_categories.html', {
        'categories': categories,
        'form': form
    })

@login_required
def invoice_time_report(request, invoice_id):
    # Fetch the invoice
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
    
    # Fetch all timesheet entries linked to THIS invoice
    entries = TimesheetEntry.objects.filter(
        invoice=invoice, 
        user=request.user
    ).select_related('category', 'client').order_by('date')

    # Grouping by category for a cleaner report
    report_data = defaultdict(list)
    total_hours = 0
    for entry in entries:
        report_data[entry.category.name if entry.category else "Standard"].append(entry)
        total_hours += entry.hours

    return render(request, 'timesheets/reports/invoice_detail.html', {
        'invoice': invoice,
        'report_data': dict(report_data),
        'total_hours': total_hours,
        'entries': entries
    })


@login_required
def manage_categories(request):
    categories = WorkCategory.objects.filter(user=request.user)
    if request.method == 'POST':
        form = WorkCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, "Category created!")
            return redirect('timesheets:manage_categories')
    else:
        form = WorkCategoryForm()
    
    return render(request, 'timesheets/manage_categories.html', {
        'categories': categories,
        'form': form
    })


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
            
            # --- FIX: Capture the Category ID ---
            category_id = request.POST.get('category')
            if category_id:
                entry.category_id = category_id
            
            if not entry.hourly_rate or entry.hourly_rate == 0:
                entry.hourly_rate = entry.client.default_hourly_rate

            meta_data = {}
            for key, value in request.POST.items():
                if key.startswith('meta_'):
                    field_name = key.replace('meta_', '')
                    if value.strip():
                        meta_data[field_name] = value
            
            entry.metadata = meta_data
            entry.save()
            messages.success(request, f"Logged {entry.hours}h for {entry.client.name}.")
        else:
            messages.error(request, "Please correct the errors below.")
    
    return redirect('timesheets:timesheet_list')



@login_required
def edit_entry(request, pk):
    entry = get_object_or_404(TimesheetEntry, pk=pk, user=request.user)

    if request.method == 'POST':
        form = TimesheetEntryForm(request.POST, instance=entry)
        if form.is_valid():
            entry = form.save(commit=False)

            category_id = request.POST.get('category')
            if category_id:
                entry.category_id = category_id

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
    # 1. Get the user's business profile settings
    try:
        profile = request.user.profile 
    except AttributeError: # Handles cases where profile isn't linked
        messages.error(request, "Please set up your Business Profile before generating invoices.")
        return redirect('core:edit_profile')

    if request.method != 'POST':
        return redirect('timesheets:timesheet_list')

    selected_ids = request.POST.getlist('selected_entries')
    if not selected_ids:
        messages.warning(request, "Select entries first.")
        return redirect('timesheets:timesheet_list')

    with transaction.atomic():
        # Select for update prevents other processes from touching these entries during calculation
        entries = TimesheetEntry.objects.select_for_update().filter(
            id__in=selected_ids, 
            user=request.user, 
            is_billed=False
        ).select_related('client', 'category')

        if not entries.exists():
            messages.info(request, "No unbilled entries found for the selection.")
            return redirect('timesheets:timesheet_list')

        # Group entries by Client
        client_map = defaultdict(list)
        for entry in entries:
            client_map[entry.client].append(entry)

        for client, client_entries in client_map.items():
            # Determine Tax Mode based on Business Profile
            # We use FULL if registered, otherwise NONE
            initial_tax_mode = Invoice.TaxMode.FULL if profile.is_vat_registered else Invoice.TaxMode.NONE

            # 2. Create the Invoice Header
            invoice = Invoice.objects.create(
                user=request.user,
                client=client,
                due_date=timezone.now().date() + timedelta(days=client.payment_terms or 14),
                tax_mode=initial_tax_mode,
                status=Invoice.Status.DRAFT
            )

            # 3. Aggregate Work Logs into Line Items (Desc + Rate)
            line_items = defaultdict(Decimal) 
            for entry in client_entries:
                key = (entry.description, entry.hourly_rate)
                line_items[key] += entry.hours
                
                # Link the original entry to the invoice for the detailed LaTeX report
                entry.is_billed = True
                entry.invoice = invoice
                entry.save()

            # 4. Create the Invoice Items
            for (desc, rate), total_h in line_items.items():
                InvoiceItem.objects.create(
                    invoice=invoice, 
                    description=desc, 
                    quantity=total_h, 
                    unit_price=rate,
                    is_taxable=profile.is_vat_registered
                )

            # 5. FINAL STEP: Sync the Snapshots
            # We must do this AFTER items are created so the math is not zero
            invoice.sync_totals()
            invoice.save()

        messages.success(request, f"Generated {len(client_map)} invoice(s) as drafts.")

    return redirect('invoices:invoice_list')