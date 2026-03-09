import os

# --- 1. LIST & DASHBOARD ---
import subprocess
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.generic import ListView

import items
from clients.models import Client
from invoices.models import Invoice

from .forms import TimesheetEntryForm, WorkCategoryForm

# Internal App Imports
from .models import TimesheetEntry, WorkCategory

# Try importing Event from events app (optional, for event-based category creation)
try:
    from events.models import Event
except ImportError:
    Todo = None


@login_required
def get_client_rate(request):
    client_id = request.GET.get("client")
    client = get_object_or_404(Client, id=client_id, user=request.user)
    # Return just the input field with the new value
    return HttpResponse(
        f'<input type="number" name="hourly_rate" id="id_hourly_rate" value="{client.default_hourly_rate}" class="form-control">'
    )


@login_required
def export_metadata_pdf(request, invoice_id):
    try:
        invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
        # Fetch entries linked to this invoice
        entries = TimesheetEntry.objects.filter(invoice=invoice).select_related("category").order_by("date")

        if not entries.exists():
            messages.error(request, "No timesheet entries found for this invoice.")
            return redirect("invoices:invoice_detail", pk=invoice_id)

        # Group by Category Name
        grouped_entries = defaultdict(list)
        for entry in entries:
            cat_name = entry.category.name if entry.category else "General"
            # Escape LaTeX special characters in category name
            cat_name = (
                cat_name.replace("&", r"\&")
                .replace("$", r"\$")
                .replace("%", r"\%")
                .replace("_", r"\_")
                .replace("^", r"\textasciicircum{}")
                .replace("~", r"\textasciitilde{}")
            )
            grouped_entries[cat_name].append(entry)

        context = {
            "invoice_number": invoice.number,
            "client_name": invoice.client.name,
            "date_generated": timezone.now().strftime("%d %b %Y"),
            "grouped_data": dict(grouped_entries),  # Pass the dictionary
            "total_hours": sum(e.hours for e in entries),
        }

        # 1. Render the LaTeX string
        tex_content = render_to_string("timesheets/reports/metadata_report.tex", context)

        # 2. Save to temporary file and compile
        temp_dir = os.path.join(settings.BASE_DIR, "tmp")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        tex_file_path = os.path.join(temp_dir, f"report_{invoice.id}.tex")
        with open(tex_file_path, "w") as f:
            f.write(tex_content)

        # Run pdflatex (ensure pdflatex is installed on your server)
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-output-directory", temp_dir, tex_file_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Log the actual error for debugging
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"pdflatex error for invoice {invoice_id}:")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            messages.error(request, "Failed to generate timesheet PDF. Check server logs for LaTeX error.")
            return redirect("invoices:invoice_detail", pk=invoice_id)

        # 3. Return the PDF
        pdf_path = tex_file_path.replace(".tex", ".pdf")
        if not os.path.exists(pdf_path):
            messages.error(request, "PDF file was not generated successfully.")
            return redirect("invoices:invoice_detail", pk=invoice_id)

        with open(pdf_path, "rb") as f:
            response = HttpResponse(f.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="Work_Log_{invoice.number}.pdf"'
            return response

    except Exception as e:
        messages.error(request, f"Error generating timesheet report: {str(e)}")
        return redirect("invoices:invoice_detail", pk=invoice_id)


@login_required
def manage_categories(request):
    # Fetch all categories belonging to the user
    categories = WorkCategory.objects.filter(user=request.user).order_by("name")

    if request.method == "POST":
        form = WorkCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, f"Category '{category.name}' created successfully!")
            return redirect("timesheets:manage_categories")
    else:
        form = WorkCategoryForm()

    return render(request, "timesheets/manage_categories.html", {"categories": categories, "form": form})


@login_required
def invoice_time_report(request, invoice_id):
    # Fetch the invoice
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)

    # Fetch all timesheet entries linked to THIS invoice
    entries = (
        TimesheetEntry.objects.filter(invoice=invoice, user=request.user)
        .select_related("category", "client")
        .order_by("date")
    )

    # Grouping by category for a cleaner report
    report_data = defaultdict(list)
    total_hours = 0
    for entry in entries:
        report_data[entry.category.name if entry.category else "Standard"].append(entry)
        total_hours += entry.hours

    return render(
        request,
        "timesheets/reports/invoice_detail.html",
        {"invoice": invoice, "report_data": dict(report_data), "total_hours": total_hours, "entries": entries},
    )


@login_required
def manage_categories(request):
    categories = WorkCategory.objects.filter(user=request.user)
    if request.method == "POST":
        form = WorkCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, "Category created!")
            return redirect("timesheets:manage_categories")
    else:
        form = WorkCategoryForm()

    return render(request, "timesheets/manage_categories.html", {"categories": categories, "form": form})


@login_required
def edit_category(request, pk):
    category = get_object_or_404(WorkCategory, id=pk, user=request.user)
    if request.method == "POST":
        form = WorkCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated!")
            return redirect("timesheets:manage_categories")
    else:
        form = WorkCategoryForm(instance=category)
    
    return render(request, "timesheets/edit_category.html", {"form": form, "category": category})


@login_required
def delete_category(request, pk):
    category = get_object_or_404(WorkCategory, id=pk, user=request.user)
    if request.method == "POST":
        category_name = category.name
        category.delete()
        messages.success(request, f"Category '{category_name}' deleted!")
        return redirect("timesheets:manage_categories")
    
    return render(request, "timesheets/delete_category.html", {"category": category})


@login_required
def get_category_fields(request):
    category_id = request.GET.get("category")
    if category_id:
        category = get_object_or_404(WorkCategory, id=category_id, user=request.user)
        # category.metadata_schema is your list like ['Attendees', 'Location']
        return render(request, "timesheets/includes/category_fields.html", {"schema": category.metadata_schema})
    return HttpResponse("")  # Return nothing if "Standard Work" is selected


class TimesheetListView(LoginRequiredMixin, ListView):
    model = TimesheetEntry
    template_name = "timesheets/timesheet_list.html"
    context_object_name = "entries"

    def get_queryset(self):
        """Only show uninvoiced items in the main table view."""
        return TimesheetEntry.objects.filter(user=self.request.user, is_billed=False).order_by("-date", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        start_of_week = today - timedelta(days=today.weekday())
        start_of_month = today.replace(day=1)

        # FETCH CATEGORIES FOR THE MODAL
        categories = WorkCategory.objects.filter(user=self.request.user).order_by("name")
        
        # Create form
        form = TimesheetEntryForm(user=self.request.user)

        clients = (
            Client.objects.filter(user=self.request.user)
            .annotate(
                weekly_actual=Coalesce(
                    Sum("timesheets__hours", filter=Q(timesheets__date__gte=start_of_week)),
                    Value(0, output_field=DecimalField()),
                ),
                monthly_actual=Coalesce(
                    Sum("timesheets__hours", filter=Q(timesheets__date__gte=start_of_month)),
                    Value(0, output_field=DecimalField()),
                ),
            )
            .order_by("name")
        )

        client_stats = []
        for c in clients:
            client_stats.append(
                {
                    "client": c,
                    "weekly_actual": c.weekly_actual,
                    "weekly_target": c.weekly_target_hours,
                    "weekly_percent": float((c.weekly_actual / c.weekly_target_hours * 100))
                    if c.weekly_target_hours > 0
                    else 0,
                }
            )

        all_month_qs = TimesheetEntry.objects.filter(user=self.request.user, date__gte=start_of_month)
        totals = all_month_qs.aggregate(total_hours=Sum("hours"), total_value=Sum(F("hours") * F("hourly_rate")))

        total_val = totals["total_value"] or Decimal("0.00")
        target_amount = Decimal("50000.00")

        invoices = Invoice.objects.filter(user=self.request.user).order_by("-date_issued")
        context.update(
            {
                "client_stats": client_stats,
                "clients": clients,
                "categories": categories,
                "total_hours": totals["total_hours"] or 0,
                "total_value": total_val,
                "target_amount": target_amount,
                "progress_percent": float(min((total_val / target_amount) * 100, 100)) if target_amount > 0 else 0,
                "timesheet_form": form,
                "invoices": invoices,
            }
        )
        return context


# --- 2. LOGGING, EDITING & DELETION ---


@login_required
def log_time(request):
    if request.method == "POST":
        form = TimesheetEntryForm(request.POST, user=request.user)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            
            # Check calendar completion gate one more time before saving
            if entry.todo:
                is_ready, reason, recommendations = entry.todo.validate_timesheet_readiness()
                if not is_ready:
                    error_msg = f"Cannot create timesheet: {reason}\n\n"
                    if recommendations:
                        error_msg += "How to fix:\n" + "\n".join(f"• {rec}" for rec in recommendations)
                    messages.error(request, error_msg)
                    return redirect("timesheets:timesheet_list")
            
            entry.save()
            messages.success(request, f"✓ Logged {entry.hours} hours on {entry.date}")
            return redirect("timesheets:timesheet_list")
        else:
            messages.error(request, "Please correct the errors below.")
            return redirect("timesheets:timesheet_list")

    return redirect("timesheets:timesheet_list")


@login_required
def edit_entry(request, pk):
    entry = get_object_or_404(TimesheetEntry, pk=pk, user=request.user)

    if entry.is_billed:
        messages.error(request, "Cannot edit invoiced entries.")
        return redirect("timesheets:timesheet_list")

    if request.method == "POST":
        form = TimesheetEntryForm(request.POST, instance=entry, user=request.user)
        if form.is_valid():
            # Manually handle category from POST (try regular field first, then backup)
            category_id = request.POST.get("category") or request.POST.get("category_hidden")
            if category_id:
                entry.category_id = category_id
            else:
                entry.category = None
            
            entry = form.save(commit=False)

            # Re-capture metadata during edit
            meta_data = {}
            for key, value in request.POST.items():
                if key.startswith("meta_"):
                    meta_data[key.replace("meta_", "")] = value

            entry.metadata = meta_data
            entry.save()
            messages.success(request, "Entry updated.")
            return redirect("timesheets:timesheet_list")
        else:
            messages.error(request, "Please correct the errors below.")
            return redirect("timesheets:timesheet_list")

    return redirect("timesheets:timesheet_list")


@login_required
def delete_entry(request, pk):
    entry = get_object_or_404(TimesheetEntry, pk=pk, user=request.user)
    if entry.is_billed:
        messages.error(request, "Cannot delete invoiced entries.")
    else:
        entry.delete()
        messages.success(request, "Timesheet deleted.")
    return redirect("timesheets:timesheet_list")


# --- 3. CONSOLIDATED INVOICE GENERATOR ---


@login_required
def generate_invoice_bulk(request):
    # 1. Get the user's business profile settings
    try:
        profile = request.user.profile
    except AttributeError:  # Handles cases where profile isn't linked
        messages.error(request, "Please set up your Business Profile before generating invoices.")
        return redirect("core:edit_profile")

    if request.method != "POST":
        return redirect("timesheets:timesheet_list")

    selected_ids = request.POST.getlist("selected_entries")
    if not selected_ids:
        messages.warning(request, "Select entries first.")
        return redirect("timesheets:timesheet_list")

    with transaction.atomic():
        # Use manager method to check if timesheets can be invoiced
        can_invoice, count_already_invoiced = TimesheetEntry.objects.can_be_invoiced(selected_ids)
        
        if not can_invoice:
            messages.error(
                request,
                f"Cannot create invoice: {count_already_invoiced} selected timesheet(s) are already linked to invoice(s). "
                "Timesheets can only be invoiced once."
            )
            return redirect("timesheets:timesheet_list")
        
        # Select for update prevents other processes from touching these entries during calculation
        entries = (
            TimesheetEntry.objects.select_for_update(of=("self",))
            .filter(id__in=selected_ids, user=request.user, is_billed=False, invoice__isnull=True)
            .select_related("client", "category")
        )

        if not entries.exists():
            messages.info(request, "No unbilled entries found for the selection.")
            return redirect("timesheets:timesheet_list")

        # Group entries by Client
        client_map = defaultdict(list)
        for entry in entries:
            client_map[entry.client].append(entry)

        flagged_count = 0
        for client, client_entries in client_map.items():
            # Create the Invoice Header
            invoice = Invoice.objects.create(
                user=request.user,
                client=client,
                due_date=timezone.now().date() + timedelta(days=client.payment_terms or 14),
                status=Invoice.Status.DRAFT,
            )

            # 3. Link timesheet entries to invoice (no Item duplication)
            for entry in client_entries:
                entry.is_billed = True
                entry.invoice = invoice
                entry.save()

            # 4. FINAL STEP: Sync the Snapshots
            # Invoice calculations will use billed_timesheets directly (no Items created)
            invoice.sync_totals()
            invoice.save()

            # 6. Add audit logging
            try:
                from core.models import BillingAuditLog, AuditHistory
                from core.utils import get_anomaly_status

                is_anomaly, comment, audit_context = get_anomaly_status(request.user, invoice)
                # Prevent duplicate audit logs for same invoice (use get_or_create)
                BillingAuditLog.objects.get_or_create(
                    user=request.user,
                    invoice=invoice,
                    defaults={
                        "is_anomaly": is_anomaly,
                        "ai_comment": comment,
                        "details": {"total": float(invoice.total_amount), "source": "timesheet_ui_billing"},
                    }
                )
                
                # Create audit history record for learning
                AuditHistory.objects.create(
                    user=request.user,
                    invoice=invoice,
                    checks_run=audit_context.get("checks_run", []),
                    flags_raised=[c for c in comment.split(" | ") if c != "OK"],
                    comparison_invoices_count=audit_context.get("comparison_invoices_count", 0),
                    is_flagged=is_anomaly,
                    comparison_mean=audit_context.get("comparison_mean"),
                    comparison_stddev=audit_context.get("comparison_stddev"),
                    comparison_cv=audit_context.get("comparison_cv"),
                )
                if is_anomaly:
                    flagged_count += 1
                    messages.warning(
                        request,
                        mark_safe(
                            f"⚠️ Invoice #{invoice.number} flagged: {comment} <a href='{reverse('invoices:billing_audit_report')}' class='alert-link'>Review in Audit</a>"
                        ),
                        extra_tags="safe",
                    )
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.error(f"Failed to audit timesheet invoice {invoice.id}: {e}")
                # Don't fail the creation just because audit failed

        messages.success(
            request,
            f"Generated {len(client_map)} invoice(s) as drafts."
            + (f" {flagged_count} flagged by audit." if flagged_count > 0 else ""),
        )

    return redirect("invoices:invoice_list")
