from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import BooleanField, Case, F, Prefetch, Q, Sum, When
from django.db.models.functions import Coalesce
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from google import genai

from clients.models import Client
from core.decorators import setup_required
from core.models import BillingAuditLog, UserProfile
from core.utils import get_anomaly_status
from invoices.models import Coupon, Invoice, InvoiceEmailStatusLog
from items.models import Item
from timesheets.models import TimesheetEntry

from .forms import InvoiceForm, VATPaymentForm
from .models import Payment, TaxPayment, VATReport
from .utils import email_invoice_to_client, generate_invoice_pdf


@login_required
@require_POST
def mark_anomaly_sorted(request, pk):
    """Clear an anomaly flag and send the invoice to client."""
    log = get_object_or_404(BillingAuditLog, pk=pk, user=request.user)
    log.is_anomaly = False
    log.save()
    invoice = log.invoice
    from django.contrib import messages

    from .utils import email_invoice_to_client

    if invoice:
        # Pass force_send=True to bypass anomaly check since we just cleared it
        sent = email_invoice_to_client(invoice, force_send=True)
        if sent:
            messages.success(
                request, f"✓ Invoice #{invoice.number} cleared and sent to {invoice.client.email} successfully."
            )
        else:
            messages.error(
                request,
                f"✗ Anomaly cleared, but invoice #{invoice.number} could not be sent. Check email address or try manual resend.",
            )
    else:
        messages.error(request, "Invoice not found.")
    return redirect("invoices:billing_audit_report")


@login_required
@require_POST
def cancel_invoice_from_audit(request, pk):
    """Cancel an invoice from the audit report."""
    log = get_object_or_404(BillingAuditLog, pk=pk, user=request.user)
    invoice = log.invoice
    from django.contrib import messages

    if not invoice:
        messages.error(request, "Invoice not found.")
        return redirect("invoices:billing_audit_report")

    # Prevent cancelling paid invoices
    if invoice.status == "PAID":
        messages.error(
            request, f"Cannot cancel invoice #{invoice.number} - it has already been paid. Contact support if needed."
        )
        return redirect("invoices:billing_audit_report")

    # Get cancellation reason from POST
    reason = request.POST.get("cancellation_reason", "").strip()
    if not reason:
        messages.error(request, "Please provide a reason for cancellation.")
        return redirect("invoices:billing_audit_report")

    # Cancel the invoice
    invoice.status = "CANCELLED"
    invoice.cancellation_reason = reason
    invoice.save()

    log.is_anomaly = False
    log.ai_comment = f"Cancelled by user. Reason: {reason}"
    log.save()

    messages.success(request, f"Invoice #{invoice.number} cancelled. Reason: {reason}")
    return redirect("invoices:billing_audit_report")


@login_required
@require_POST
def toggle_attach_timesheet(request, pk):
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Toggle timesheet: pk={pk}, user={request.user}")
    try:
        invoice = Invoice.objects.get(pk=pk, user=request.user)
        logger.info(
            f"Found invoice: id={invoice.id}, user={invoice.user}, attach_timesheet_to_email={invoice.attach_timesheet_to_email}"
        )
        invoice.attach_timesheet_to_email = not invoice.attach_timesheet_to_email
        invoice.save()
        logger.info(f"Updated invoice: id={invoice.id}, attach_timesheet_to_email={invoice.attach_timesheet_to_email}")
        if request.headers.get("HX-Request"):
            from django.template.loader import render_to_string

            html = render_to_string("invoices/partials/timesheet_attach_toggle_form.html", {"invoice": invoice})
            return HttpResponse(html)
        return redirect("invoices:invoice_list")
    except Invoice.DoesNotExist:
        logger.error(f"Invoice not found: pk={pk}, user={request.user}")
        if request.headers.get("HX-Request"):
            return HttpResponse(
                f'<div class="alert alert-danger">Invoice not found: pk={pk}, user={request.user}</div>'
            )
        return redirect("invoices:invoice_list")


# --- FORMSET DEFINITION ---
InvoiceItemFormSet = inlineformset_factory(
    Invoice, Item, fields=("description", "quantity", "unit_price"), extra=1, can_delete=True
)


@login_required
@setup_required
def get_payment_modal(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)

    # Get available credit balance for the client

    from invoices.models import Coupon, CreditNote

    # Use manager method for available credit
    available_credit = CreditNote.objects.get_client_credit_balance(invoice.client)

    # Get valid coupons for this user
    from django.utils import timezone

    today = timezone.now().date()
    available_coupons = (
        Coupon.objects.filter(user=request.user, is_active=True, valid_from__lte=today)
        .exclude(valid_until__lt=today)
        .exclude(max_uses=models.F("current_uses"))
        .values("id", "code", "discount_type", "discount_value")
    )

    # Get user's currency
    currency = request.user.profile.currency if hasattr(request.user, "profile") else "R"

    context = {
        "invoice": invoice,
        "available_credit": available_credit,
        "available_coupons": available_coupons,
        "currency": currency,
    }
    return render(request, "invoices/partials/payment_modal_content.html", context)


@login_required
@setup_required
def get_resend_modal(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    return render(request, "invoices/partials/resend_modal_content.html", {"invoice": invoice})


@login_required
@setup_required
def get_send_modal(request, pk):
    """Get modal for sending a DRAFT invoice/quote."""
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    return render(request, "invoices/partials/send_modal_content.html", {"invoice": invoice})


@login_required
@setup_required
def dashboard(request):
    """Main overview for the business owner."""
    invoices = Invoice.objects.filter(user=request.user).select_related("client")
    unbilled_ts = TimesheetEntry.objects.filter(user=request.user, is_billed=False).aggregate(
        total_value=Sum(F("hours") * F("hourly_rate")),
    )
    unbilled_items = Item.objects.filter(user=request.user, is_billed=False, is_recurring=False, invoice__isnull=True).aggregate(
        total_value=Sum(F("quantity") * F("unit_price"))
    )
    queued_items = Item.objects.filter(user=request.user, is_billed=False, is_recurring=True).aggregate(
        total_value=Sum(F("quantity") * F("unit_price"))
    )
    flagged_count = (
        BillingAuditLog.objects.filter(user=request.user, is_anomaly=True).exclude(invoice__status="PAID").count()
    )
    # Get counts for dashboard cards
    queued_items_count = Item.objects.filter(user=request.user, is_billed=False, is_recurring=True).count()
    unbilled_ts_count = TimesheetEntry.objects.filter(user=request.user, is_billed=False).count()
    unbilled_items_count = Item.objects.filter(user=request.user, is_billed=False, is_recurring=False, invoice__isnull=True).count()
    total_billed_invoices = invoices.exclude(status__in=["DRAFT", "DISCARDED", "CANCELLED"]).count()
    outstanding_invoices_count = invoices.exclude(status__in=["DRAFT", "PAID", "DISCARDED", "CANCELLED"]).count()
    pending_quotes_count = invoices.filter(is_quote=True).count()

    # Use manager methods for stats - centralized calculations
    user_stats = Invoice.objects.get_user_stats(request.user)
    quote_total = Invoice.objects.get_user_quote_total(request.user)
    total_outstanding = Invoice.objects.get_total_outstanding(request.user)

    # Get draft invoices separately (exclude quotes) and recent posted invoices
    draft_invoices = invoices.filter(status="DRAFT", is_quote=False).order_by("-date_issued", "-id")[:3]
    
    # Get aged drafts (DRAFT invoices past their due date) - require review
    aged_drafts = invoices.filter(status="DRAFT", is_quote=False, due_date__lt=timezone.now().date()).order_by("due_date")
    
    recent_invoices = invoices.exclude(status="DRAFT").exclude(is_quote=True).order_by("-date_issued", "-id")[:5]
    
    # Get paid invoices total
    paid_invoices = invoices.filter(status="PAID").order_by("-date_issued", "-id")[:5]
    total_paid_invoices = Payment.objects.filter(invoice__user=request.user).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    # Get revenue targets and threshold tracking
    revenue_vs_target = Invoice.objects.get_revenue_vs_target(request.user)
    vat_threshold_check = Invoice.objects.check_vat_threshold(request.user)

    context = {
        "queued_items_value": queued_items["total_value"] or Decimal("0.00"),
        "queued_items_count": queued_items_count,
        "unbilled_wip_value": (unbilled_ts["total_value"] or Decimal("0.00"))
        + (unbilled_items["total_value"] or Decimal("0.00")),
        "unbilled_ts_count": unbilled_ts_count,
        "unbilled_items_count": unbilled_items_count,
        "total_billed": Invoice.objects.get_active_billed_total(request.user),
        "total_billed_invoices": total_billed_invoices,
        "total_quotes": quote_total,
        "pending_quotes_count": pending_quotes_count,
        "total_outstanding": total_outstanding,
        "outstanding_invoices_count": outstanding_invoices_count,
        "tax_summary": Invoice.objects.get_tax_summary(request.user),
        "draft_invoices": draft_invoices,
        "aged_drafts": aged_drafts,
        "recent_invoices": recent_invoices,
        "paid_invoices": paid_invoices,
        "total_paid_invoices": total_paid_invoices,
        "flagged_count": flagged_count,
        "recent_vat_payments": TaxPayment.objects.filter(user=request.user, tax_type="VAT").order_by("-payment_date")[:5],
        "revenue_vs_target": revenue_vs_target,
        "vat_threshold_check": vat_threshold_check,
    }

    return render(request, "invoices/dashboard.html", context)


@login_required
@setup_required
def revenue_report(request):
    """Revenue reporting view with quarterly and yearly breakdowns."""
    # Get quarterly breakdown for current tax year
    quarterly_data = Invoice.objects.get_quarterly_report(request.user)
    
    # Get yearly summary for last 3 years
    yearly_summary = Invoice.objects.get_yearly_summary(request.user, num_years=3)
    
    # Get current year-to-date
    revenue_vs_target = Invoice.objects.get_revenue_vs_target(request.user)
    
    context = {
        'quarterly_data': quarterly_data,
        'yearly_summary': yearly_summary,
        'revenue_vs_target': revenue_vs_target,
        'current_tax_year': request.user.profile.tax_year_type,
    }
    
    return render(request, 'invoices/revenue_report.html', context)


@login_required
@setup_required
def invoice_list(request):
    today = timezone.now().date()

    invoice_queryset = (
        Invoice.objects.filter(user=request.user)
        .select_related("client")
        .prefetch_related(
            Prefetch(
                "delivery_logs",
                queryset=InvoiceEmailStatusLog.objects.order_by("-created_at"),
            )
        )
        .annotate(
            is_overdue=Case(
                When(Q(due_date__lt=today) & ~Q(status__in=["PAID", "DRAFT", "CANCELLED"]), then=True),
                default=False,
                output_field=BooleanField(),
            )
        )
    )

    status_filter = request.GET.get("status")
    if status_filter == "UNPAID":
        invoice_queryset = invoice_queryset.exclude(status="PAID")

    # Exclude rejected quotes from list by default
    invoice_queryset = invoice_queryset.exclude(quote_status="REJECTED")

    overdue_filter = request.GET.get("overdue") == "true"
    if overdue_filter:
        invoice_queryset = invoice_queryset.filter(is_overdue=True)

    type_filter = request.GET.get("type")
    if type_filter == "TIMESHEET":
        invoice_queryset = invoice_queryset.filter(billed_timesheets__isnull=False).distinct()
    elif type_filter == "PRODUCT":
        invoice_queryset = invoice_queryset.filter(billed_items__isnull=False).distinct()

    search_query = request.GET.get("q", "").strip()
    if search_query:
        invoice_queryset = invoice_queryset.filter(
            Q(number__icontains=search_query)
            | Q(client__name__icontains=search_query)
            | Q(client__email__icontains=search_query)
        )

    # Handle sorting
    sort_param = request.GET.get("sort", "-date_issued")
    allowed_sorts = {
        "number": "number",
        "-number": "-number",
        "client__name": "client__name",
        "-client__name": "-client__name",
        "total_amount": "total_amount",
        "-total_amount": "-total_amount",
        "date_issued": "date_issued",
        "-date_issued": "-date_issued",
        "status": "status",
        "-status": "-status",
        "billing_type": "billing_type",
        "-billing_type": "-billing_type",
    }
    if sort_param not in allowed_sorts:
        sort_param = "-date_issued"

    invoice_queryset = invoice_queryset.order_by(sort_param, "-id")

    # Check if user wants to see all invoices or use pagination
    show_all = request.GET.get("show_all") == "true"
    total_count = invoice_queryset.count()
    
    if show_all:
        # Show all invoices without pagination
        page_obj = invoice_queryset
        displayed_count = total_count
    else:
        # Use pagination (5 per page)
        paginator = Paginator(invoice_queryset, 5)
        page_obj = paginator.get_page(request.GET.get("page"))
        displayed_count = len(page_obj)
    
    # Attach latest delivery status to each invoice for display
    for invoice in page_obj:
        invoice.latest_delivery_status = invoice.get_latest_delivery_status()

    # Build sort URLs
    def toggle_sort(field):
        """Toggle sort direction for a field"""
        if sort_param == field:
            return "-" + field
        elif sort_param == "-" + field:
            return field
        else:
            return "-" + field

    # If this is an HTMX refresh request, return only the table fragment
    if request.headers.get("HX-Request"):
        return render(
            request,
            "invoices/invoice_list_fragment.html",
            {
                "invoices": page_obj,
                "search_query": search_query,
                "status_filter": status_filter,
                "type_filter": type_filter,
                "overdue_filter": overdue_filter,
                "current_sort": sort_param,
                "toggle_sort": toggle_sort,
                "total_count": total_count,
                "displayed_count": displayed_count,
                "show_all": show_all,
            },
        )

    return render(
        request,
        "invoices/invoice_list.html",
        {
            "invoices": page_obj,
            "search_query": search_query,
            "status_filter": status_filter,
            "type_filter": type_filter,
            "overdue_filter": overdue_filter,
            "current_sort": sort_param,
            "toggle_sort": toggle_sort,
            "total_count": total_count,
            "displayed_count": displayed_count,
            "show_all": show_all,
        },
    )


@login_required
@setup_required
def invoice_detail(request, pk):
    from collections import defaultdict
    from decimal import Decimal
    
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    # Auto-fix orphaned invoices (have delivery logs but wrong status)
    invoice.sync_status_with_delivery()
    
    # Group timesheets by category for aggregated display
    grouped_timesheets = defaultdict(lambda: {"hours": Decimal("0.00"), "hourly_rate": Decimal("0.00"), "entries": []})
    for ts in invoice.billed_timesheets.all().select_related("category"):
        category_name = ts.category.name if ts.category else "Timesheet"
        key = (category_name, ts.hourly_rate)
        grouped_timesheets[key]["hours"] += ts.hours
        grouped_timesheets[key]["hourly_rate"] = ts.hourly_rate  # All in same group should have same rate
        grouped_timesheets[key]["entries"].append(ts)
    
    # Convert to sorted list for consistent display order
    grouped_timesheets_list = [
        {
            "category_name": key[0],
            "hourly_rate": key[1],
            "hours": data["hours"],
            "total_value": data["hours"] * data["hourly_rate"],
            "entries": data["entries"],
        }
        for key, data in sorted(grouped_timesheets.items())
    ]
    
    return render(request, "invoices/invoice_detail.html", {
        "invoice": invoice,
        "grouped_timesheets": grouped_timesheets_list,
    })


@login_required
@setup_required
def invoice_create(request):
    initial_data = {}
    client_id = request.GET.get("client_id")
    if client_id:
        initial_data["client"] = get_object_or_404(Client, id=client_id, user=request.user)

    if request.method == "POST":
        form = InvoiceForm(request.POST)
        formset = InvoiceItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                invoice = form.save(commit=False)
                invoice.user = request.user
                invoice.save()
                formset.instance = invoice
                formset.save()
                Invoice.objects.update_totals(invoice)
                invoice.refresh_from_db()

                try:
                    from core.models import AuditHistory
                    is_anomaly, comment, audit_context = get_anomaly_status(request.user, invoice)
                    # Prevent duplicate audit logs for same invoice (use get_or_create)
                    BillingAuditLog.objects.get_or_create(
                        user=request.user,
                        invoice=invoice,
                        defaults={
                            "is_anomaly": is_anomaly,
                            "ai_comment": comment,
                            "details": {"total": str(invoice.total_amount), "source": "manual_create"},
                        }
                    )
                    
                    # Create audit history record for learning
                    AuditHistory.objects.filter(invoice=invoice).delete()
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
                        messages.warning(
                            request,
                            mark_safe(
                                f"⚠️ Invoice flagged by audit system: {comment} <a href='{reverse('invoices:billing_audit_report')}' class='alert-link'>Review in Audit Report</a>"
                            ),
                            extra_tags="safe",
                        )
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to audit new invoice {invoice.id}: {e}")
                    # Still save the invoice even if audit fails

            messages.success(request, "Invoice created.")
            return redirect("invoices:invoice_detail", pk=invoice.pk)
    else:
        form = InvoiceForm(initial=initial_data)
        formset = InvoiceItemFormSet()
    return render(request, "invoices/invoice_form.html", {"form": form, "formset": formset, "is_edit": False})


@login_required
@setup_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    if invoice.status != "DRAFT":
        messages.warning(request, "Only Draft invoices can be edited.")
        return redirect("invoices:invoice_detail", pk=invoice.pk)

    if request.method == "POST":
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, instance=invoice)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
                Invoice.objects.update_totals(invoice)
                invoice.refresh_from_db()

                # Re-audit the invoice after edits
                try:
                    from core.models import AuditHistory
                    is_anomaly, comment, audit_context = get_anomaly_status(request.user, invoice)
                    BillingAuditLog.objects.filter(invoice=invoice).delete()
                    BillingAuditLog.objects.create(
                        user=request.user,
                        invoice=invoice,
                        is_anomaly=is_anomaly,
                        ai_comment=comment,
                        details={"total": str(invoice.total_amount), "source": "manual_edit"},
                    )
                    
                    # Update audit history record
                    AuditHistory.objects.filter(invoice=invoice).delete()
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
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to audit edited invoice {invoice.id}: {e}")
                    # Still save the invoice even if audit fails
            return redirect("invoices:invoice_detail", pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice)
    return render(request, "invoices/invoice_form.html", {"form": form, "formset": formset, "is_edit": True})


@login_required
@setup_required
def duplicate_invoice(request, pk):
    original = get_object_or_404(Invoice, pk=pk, user=request.user)
    with transaction.atomic():
        new_invoice = Invoice.objects.create(
            user=request.user,
            client=original.client,
            status="DRAFT",
            billing_type=original.billing_type,
            due_date=timezone.now().date() + timedelta(days=30),
        )
        for item in original.billed_items.all():
            Item.objects.create(
                user=request.user,
                client=original.client,
                invoice=new_invoice,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                is_billed=False,
            )
        Invoice.objects.update_totals(new_invoice)
    messages.success(request, f"Duplicated as Draft #{new_invoice.id}")
    return redirect("invoices:invoice_edit", pk=new_invoice.pk)


@login_required
@setup_required
def bulk_post(request):
    if request.method == "POST":
        select_all_matching = request.POST.get("select_all_matching") == "true"
        
        if select_all_matching:
            # Reconstruct queryset with the same filters from the list view
            from django.db.models import BooleanField, Case, Q, When
            today = timezone.now().date()
            
            invoice_queryset = (
                Invoice.objects.filter(user=request.user)
                .annotate(
                    is_overdue=Case(
                        When(Q(due_date__lt=today) & ~Q(status__in=["PAID", "DRAFT", "CANCELLED"]), then=True),
                        default=False,
                        output_field=BooleanField(),
                    )
                )
            )
            
            # Apply the same filters
            status_filter = request.POST.get("status")
            if status_filter == "UNPAID":
                invoice_queryset = invoice_queryset.exclude(status="PAID")
            
            # Exclude rejected quotes
            invoice_queryset = invoice_queryset.exclude(quote_status="REJECTED")
            
            overdue_filter = request.POST.get("overdue") == "true"
            if overdue_filter:
                invoice_queryset = invoice_queryset.filter(is_overdue=True)
            
            search_query = request.POST.get("q", "").strip()
            if search_query:
                invoice_queryset = invoice_queryset.filter(
                    Q(number__icontains=search_query)
                    | Q(client__name__icontains=search_query)
                    | Q(client__email__icontains=search_query)
                )
            
            # Only include DRAFT invoices that are NOT quotes
            invoice_queryset = invoice_queryset.filter(status="DRAFT", is_quote=False)
            invoice_ids = list(invoice_queryset.values_list("id", flat=True))
        else:
            invoice_ids = request.POST.getlist("invoice_ids")
        
        # Exclude quotes from bulk posting - only post invoices
        invoices = Invoice.objects.filter(id__in=invoice_ids, user=request.user, status="DRAFT", is_quote=False)
        count = 0
        flagged_count = 0
        
        for inv in invoices:
            try:
                from core.models import AuditHistory
                is_anomaly, comment, audit_context = get_anomaly_status(request.user, inv)
                BillingAuditLog.objects.create(
                    user=request.user,
                    invoice=inv,
                    is_anomaly=is_anomaly,
                    ai_comment=comment,
                    details={"total": float(inv.total_amount), "source": "bulk_post"},
                )
                
                # Create or update audit history record for learning
                AuditHistory.objects.filter(invoice=inv).delete()
                AuditHistory.objects.create(
                    user=request.user,
                    invoice=inv,
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
                    # NOTE: Do NOT block - just log the audit flag
                    # Continue processing the invoice normally
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.error(f"Failed to audit invoice {inv.id} in bulk_post: {e}")
                # Continue anyway even if audit fails

            # Queue invoice for async sending via Celery
            try:
                from invoices.tasks import send_invoice_async
                send_invoice_async.delay(inv.id)
                count += 1
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to queue invoice {inv.id} for sending: {e}")

        message = f"Queued {count} invoice(s) for sending"
        if flagged_count > 0:
            message += f" ({flagged_count} flagged - review in audit)"
        messages.success(request, message)
    return redirect("invoices:invoice_list")


@login_required
@setup_required
def mark_invoice_paid(request, pk):
    if request.method != "POST":
        return redirect("invoices:invoice_detail", pk=pk)

    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    balance = invoice.balance_due

    if balance > 0:
        try:
            with transaction.atomic():
                Payment.objects.create(
                    user=request.user, invoice=invoice, amount=balance, reference="Marked Paid (Full)"
                )
            messages.success(request, f"Invoice #{invoice.number} settled.")
        except Exception as e:
            messages.error(request, f"Payment error: {str(e)}")

    return redirect(request.META.get("HTTP_REFERER", "invoices:dashboard"))


@login_required
@setup_required
def record_payment(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    next_url = request.META.get("HTTP_REFERER") or reverse("invoices:dashboard")

    if request.method == "POST":
        try:
            amount_str = request.POST.get("amount", "0").replace(",", "").strip()
            amount = Decimal(amount_str)
            credit_to_apply_str = request.POST.get("credit_to_apply", "0").replace(",", "").strip()
            credit_to_apply = Decimal(credit_to_apply_str)

            # Validate that at least one payment method is used
            if amount <= 0 and credit_to_apply <= 0:
                messages.error(request, "Please enter a payment amount or apply credit.")
                if request.headers.get("HX-Request"):
                    response = HttpResponse(status=204)
                    response["HX-Redirect"] = next_url
                    return response
                return redirect(next_url)

            with transaction.atomic():
                # Apply coupon if requested
                coupon_discount = Decimal("0.00")
                coupon_code = request.POST.get("coupon_code", "").strip()
                if coupon_code:
                    try:
                        coupon = Coupon.objects.get(user=request.user, code=coupon_code)
                        if coupon.is_valid():
                            coupon_discount = coupon.apply_discount(invoice.balance_due)
                            coupon.use()
                        else:
                            messages.warning(request, f"Coupon '{coupon_code}' is no longer valid.")
                    except Coupon.DoesNotExist:
                        messages.warning(request, f"Coupon '{coupon_code}' not found.")

                # Apply credit notes if requested
                credits_used = Decimal("0.00")
                if credit_to_apply > 0:
                    from invoices.models import CreditNote

                    # Get available credit notes for this client, ordered by date
                    available_credits = CreditNote.objects.filter(
                        user=request.user, client=invoice.client, balance__gt=0
                    ).order_by("issued_date")

                    remaining_to_apply = credit_to_apply

                    for credit_note in available_credits:
                        if remaining_to_apply <= 0:
                            break

                        # Calculate how much of this credit to use
                        amount_to_use = min(remaining_to_apply, credit_note.balance)

                        # Deduct from credit note balance
                        credit_note.balance -= amount_to_use

                        # If credit note is fully used, delete it
                        if credit_note.balance <= 0:
                            credit_note.delete()
                        else:
                            credit_note.save()

                        credits_used += amount_to_use
                        remaining_to_apply -= amount_to_use

                # Record the payment (after credits subtracted and coupon applied)
                final_payment_amount = amount - coupon_discount

                # Get user's currency for messages
                currency = request.user.profile.currency if hasattr(request.user, "profile") else "R"

                # Allow payments with amount > 0, or credit-only payments
                if final_payment_amount > 0 or credits_used > 0 or coupon_discount > 0:
                    payment = Payment.objects.create(
                        user=request.user,
                        invoice=invoice,
                        amount=max(final_payment_amount, Decimal("0.00")),  # Ensure amount is never negative
                        credit_applied=credits_used,  # Store the credit amount that was applied
                        reference=request.POST.get("reference", "Manual Payment"),
                    )

                    # Check if invoice is now fully paid and update status
                    invoice.refresh_from_db()
                    if invoice.balance_due <= 0 and invoice.status not in ["PAID", "CANCELLED"]:
                        invoice.status = "PAID"
                        invoice.save()

                    # Build success message with all payment components
                    message_parts = []
                    if final_payment_amount > 0:
                        message_parts.append(f"{currency}{final_payment_amount:.2f} cash")
                    if credits_used > 0:
                        message_parts.append(f"{currency}{credits_used:.2f} credit")
                    if coupon_discount > 0:
                        message_parts.append(f"{currency}{coupon_discount:.2f} coupon")

                    if len(message_parts) == 1:
                        payment_desc = f"Payment recorded: {message_parts[0]}."
                    else:
                        payment_desc = f"Payment recorded: {' + '.join(message_parts)}."

                    messages.success(request, payment_desc)

            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = next_url
                return response

            return redirect(next_url)

        except ValidationError as e:
            messages.error(request, f"Error: {', '.join(e.messages)}")
        except (InvalidOperation, ValueError):
            messages.error(request, "Invalid numeric amount.")

    return redirect(next_url)


@login_required
@setup_required
def generate_invoice_pdf_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    requested_style = request.GET.get("style", "default")
    template_name = "invoice_modern.tex" if requested_style == "modern" else "invoice_template.tex"
    try:
        pdf_content = generate_invoice_pdf(invoice, template_name=template_name)
        response = HttpResponse(pdf_content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="Invoice_{invoice.pk}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"PDF Error: {str(e)}")
        return redirect("invoices:invoice_detail", pk=pk)


@login_required
@setup_required
def resend_invoice(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    if invoice.status == "DRAFT":
        messages.warning(request, "Cannot email a draft.")
    else:
        if email_invoice_to_client(invoice):
            messages.success(request, "Invoice resent.")
    return redirect(request.META.get("HTTP_REFERER", "invoices:invoice_detail"))


@login_required
def financial_assessment(request):
    today = date.today()
    start_of_month = today.replace(day=1)
    actual_billed = Invoice.objects.filter(user=request.user, date_issued__gte=start_of_month).exclude(
        status="CANCELLED"
    ).aggregate(total=Sum("subtotal_amount"))["total"] or Decimal("0.00")
    unbilled_qs = TimesheetEntry.objects.filter(user=request.user, is_billed=False)
    total_unbilled = unbilled_qs.aggregate(val=Sum(F("hours") * F("hourly_rate")))["val"] or Decimal("0.00")
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    target = user_profile.monthly_target or Decimal("50000.00")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    currency = user_profile.currency
    prompt = f"Target: {currency} {target}. Invoiced: {currency} {actual_billed}. WIP: {currency} {total_unbilled}. Assess in 2 sentences."
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        assessment_text = response.text
    except Exception:
        assessment_text = "Assessment unavailable."
    return render(
        request,
        "invoices/partials/assessment_result.html",
        {"assessment": assessment_text, "target": target, "total_progress": actual_billed + total_unbilled},
    )


@login_required
def record_vat_payment(request):
    if request.method == "POST":
        form = VATPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.user = request.user
            # Auto-generate reference if not provided
            if not payment.reference:
                from datetime import date
                today = payment.payment_date or date.today()
                month_abbr = today.strftime('%b').upper()
                year = today.year % 100  # Last 2 digits of year
                payment.reference = f"VAT{year:02d}{month_abbr}"
            payment.save()
            # Return successful response with redirect header using reverse URL
            response = HttpResponse(f"Payment of {payment.amount} recorded successfully", status=200)
            response['HX-Redirect'] = reverse("invoices:dashboard")
            return response
        else:
            # Return form with errors for HTMX to display (unprocessable entity)
            return render(request, "invoices/partials/vat_payment_form.html", {"form": form}, status=422)
    
    form = VATPaymentForm(initial={"tax_type": "VAT"})
    return render(request, "invoices/partials/vat_payment_form.html", {"form": form})


@login_required
def vat_payment_history_modal(request):
    """Get full VAT payment history with summary and detailed timeline."""
    
    # Get tax summary
    tax_summary = Invoice.objects.get_tax_summary(request.user)
    
    # Get all invoices with VAT amounts (that are posted/paid, not drafts)
    invoices_with_vat = Invoice.objects.filter(
        user=request.user
    ).exclude(
        status="DRAFT"
    ).filter(
        tax_amount__gt=0
    ).values("date_issued", "number", "tax_amount", "status").order_by("date_issued")
    
    # Get all VAT payments
    vat_payments = TaxPayment.objects.filter(user=request.user, tax_type="VAT").order_by("payment_date")
    
    # Build timeline of events
    events = []
    
    # Add invoice events - showing their current stage in VAT liability flow
    for inv in invoices_with_vat:
        # Determine the stage based on invoice status
        if inv["status"] == "PAID":
            # Liability has been COLLECTED from client
            stage = "Liability COLLECTED"
            event_type = "collected"
        else:
            # PENDING or OVERDUE = Liability only SET, not yet collected from client
            stage = "Liability SET"
            event_type = "accrued"
        
        events.append({
            "date": inv["date_issued"],
            "type": event_type,
            "description": f"Invoice #{inv['number']} - {stage}",
            "amount": inv["tax_amount"],
            "status": inv["status"],
        })
    
    # Add payment events
    for payment in vat_payments:
        events.append({
            "date": payment.payment_date,
            "type": "payment",
            "description": f"Payment to SARS - {payment.reference or '[Auto-generated]'}",
            "amount": payment.amount,
            "status": "PAID",
        })
    
    # Sort by date, then by type (accrued/collected before payment on same date)
    events.sort(key=lambda x: (x["date"], x["type"] == "payment"))
    
    # Calculate running totals
    accrued = Decimal("0.00")
    collected = Decimal("0.00")
    paid = Decimal("0.00")
    for event in events:
        if event["type"] == "accrued":
            event["accrued_running"] = accrued + event["amount"]
            event["collected_running"] = collected
            event["paid_running"] = paid
            accrued += event["amount"]
        elif event["type"] == "collected":
            # Collected invoices also contribute to accrued (they were accrued when issued)
            event["accrued_running"] = accrued + event["amount"]
            event["collected_running"] = collected + event["amount"]
            event["paid_running"] = paid
            accrued += event["amount"]
            collected += event["amount"]
        else:  # payment
            event["accrued_running"] = accrued
            event["collected_running"] = collected
            event["paid_running"] = paid + event["amount"]
            paid += event["amount"]
        
        event["outstanding_running"] = event["accrued_running"] - event["paid_running"]
    
    return render(request, "invoices/partials/vat_payment_history_modal.html", {
        "tax_summary": tax_summary,
        "events": events,
        "vat_payments": vat_payments,
        "total_vat_paid": vat_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
    })


@login_required
def export_vat_payments_csv(request):
    """Export VAT payment history with timeline as CSV."""
    import csv
    from io import StringIO
    
    # Get tax summary
    tax_summary = Invoice.objects.get_tax_summary(request.user)
    
    # Get all invoices with VAT amounts (that are posted/paid, not drafts)
    invoices_with_vat = Invoice.objects.filter(
        user=request.user
    ).exclude(
        status="DRAFT"
    ).filter(
        tax_amount__gt=0
    ).values("date_issued", "number", "tax_amount", "status").order_by("date_issued")
    
    # Get all VAT payments
    vat_payments = TaxPayment.objects.filter(user=request.user, tax_type="VAT").order_by("payment_date")
    
    # Build timeline of events
    events = []
    
    # Add invoice events - showing their current stage in VAT liability flow
    for inv in invoices_with_vat:
        # Determine the stage based on invoice status
        if inv["status"] == "PAID":
            # Liability has been COLLECTED from client
            stage = "Liability COLLECTED"
            event_type = "collected"
        else:
            # PENDING or OVERDUE = Liability only SET, not yet collected from client
            stage = "Liability SET"
            event_type = "accrued"
        
        events.append({
            "date": inv["date_issued"],
            "type": event_type,
            "description": f"Invoice #{inv['number']} - {stage}",
            "amount": inv["tax_amount"],
            "status": inv["status"],
        })
    
    # Add payment events
    for payment in vat_payments:
        events.append({
            "date": payment.payment_date,
            "type": "payment",
            "description": f"Payment to SARS - {payment.reference or '[Auto-generated]'}",
            "amount": payment.amount,
            "status": "PAID",
        })
    
    # Sort by date, then by type (accrued/collected before payment on same date)
    events.sort(key=lambda x: (x["date"], x["type"] == "payment"))
    
    # Calculate running totals
    accrued = Decimal("0.00")
    collected = Decimal("0.00")
    paid = Decimal("0.00")
    for event in events:
        if event["type"] == "accrued":
            event["accrued_running"] = accrued + event["amount"]
            event["collected_running"] = collected
            event["paid_running"] = paid
            accrued += event["amount"]
        elif event["type"] == "collected":
            # Collected invoices also contribute to accrued (they were accrued when issued)
            event["accrued_running"] = accrued + event["amount"]
            event["collected_running"] = collected + event["amount"]
            event["paid_running"] = paid
            accrued += event["amount"]
            collected += event["amount"]
        else:  # payment
            event["accrued_running"] = accrued
            event["collected_running"] = collected
            event["paid_running"] = paid + event["amount"]
            paid += event["amount"]
        
        event["outstanding_running"] = event["accrued_running"] - event["paid_running"]
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    currency = request.user.profile.currency if hasattr(request.user, "profile") else "ZAR"
    
    # Write summary
    writer.writerow(["VAT Payment History Export"])
    writer.writerow(["Generated", timezone.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])
    
    writer.writerow(["SUMMARY"])
    writer.writerow(["Liability Accrued", f"{tax_summary.get('accrued', 0):.2f}", currency])
    writer.writerow(["Liability Collected", f"{tax_summary.get('collected', 0):.2f}", currency])
    writer.writerow(["Paid to SARS", f"{tax_summary.get('paid', 0):.2f}", currency])
    writer.writerow(["Outstanding Liability", f"{tax_summary.get('outstanding', 0):.2f}", currency])
    writer.writerow([])
    
    # Write timeline
    writer.writerow(["ACTIVITY TIMELINE"])
    writer.writerow(["Date", "Event Type", "Description", "Amount", "Accrued", "Collected", "Paid", "Outstanding"])
    
    for event in events:
        writer.writerow([
            event["date"].strftime("%Y-%m-%d"),
            event["type"].upper(),
            event["description"],
            f"{event['amount']:.2f}",
            f"{event['accrued_running']:.2f}",
            f"{event['collected_running']:.2f}",
            f"{event['paid_running']:.2f}",
            f"{event['outstanding_running']:.2f}",
        ])
    
    # Return as downloadable file
    output.seek(0)
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="VAT_History_{timezone.now().strftime("%Y%m%d")}.csv"'
    return response


@login_required
def generate_vat_report(request):
    month = int(request.GET.get("month", timezone.now().month))
    year = int(request.GET.get("year", timezone.now().year))
    invoices = Invoice.objects.filter(user=request.user, date_issued__month=month, date_issued__year=year)
    totals = invoices.aggregate(net=Sum("subtotal_amount"), vat=Sum("tax_amount"))
    VATReport.objects.update_or_create(
        user=request.user,
        month=month,
        year=year,
        defaults={"net_total": totals["net"] or 0, "vat_total": totals["vat"] or 0},
    )
    messages.success(request, "Report generated.")
    return redirect("invoices:dashboard")


@login_required
def download_vat_latex(request, pk):
    report = get_object_or_404(VATReport, pk=pk, user=request.user)
    response = HttpResponse(report.latex_source, content_type="text/plain")
    filename = f"VAT_Report_{report.year}_{report.month:02d}.tex"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def delete_invoice(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    if invoice.status != "DRAFT":
        messages.error(request, "Only drafts can be deleted.")
        return redirect("invoices:invoice_detail", pk=pk)
    if request.method == "POST":
        # Reset is_billed flag on all items/timesheets linked to this invoice
        invoice.billed_items.all().update(is_billed=False)
        invoice.billed_timesheets.all().update(is_billed=False)
        invoice.delete()
        return redirect("invoices:invoice_list")
    return render(request, "invoices/invoice_confirm_delete.html", {"invoice": invoice})


@login_required
def billing_audit_report(request):
    logs = BillingAuditLog.objects.filter(user=request.user).order_by("-created_at")

    total_logs = logs.count()
    anomalies_caught = logs.filter(is_anomaly=True).count()
    catch_rate = (anomalies_caught / total_logs * 100) if total_logs > 0 else 0

    anomaly_details = logs.filter(is_anomaly=True).values_list("details", flat=True)
    potential_errors_value = sum([Decimal(str(d.get("total", 0))) for d in anomaly_details])

    success_count = logs.filter(invoice__status__in=["PENDING", "PAID"]).count()

    # Get user's currency
    currency = request.user.profile.currency if hasattr(request.user, "profile") else "R"

    context = {
        "total_logs": total_logs,
        "anomalies_caught": anomalies_caught,
        "catch_rate": round(catch_rate, 1),
        "potential_errors_value": potential_errors_value,
        "success_count": success_count,
        "recent_logs": logs[:20],
        "manual_count": logs.filter(details__source="manual_create").count(),
        "bulk_count": logs.filter(details__source="bulk_post").count(),
        "scheduler_count": logs.filter(details__source="recurring_scheduler").count(),
        "currency": currency,
    }
    return render(request, "invoices/audit_report.html", context)


@login_required
@require_POST
def toggle_quote_status(request, pk):
    """Toggle an invoice between quote and invoice."""
    from django.http import JsonResponse
    
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    invoice.is_quote = not invoice.is_quote
    invoice.save()
    
    from django.contrib import messages
    
    status = "Quote" if invoice.is_quote else "Invoice"
    messages.success(request, f"✓ Document converted to {status}")
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"is_quote": invoice.is_quote, "status": status})
    
    return redirect("invoices:invoice_detail", pk=pk)


@login_required
@require_POST
def convert_quote_to_invoice(request, pk):
    """Convert a quote to an invoice."""
    from django.contrib import messages
    
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    if not invoice.is_quote:
        messages.error(request, "This is not a quote.")
        return redirect("invoices:invoice_detail", pk=pk)
    
    invoice.is_quote = False
    # Mark that this invoice originated as a quote
    invoice.was_originally_quote = True
    invoice.quote_status = "ACCEPTED"
    # Reset email flags so the invoice can be sent again (separately from the quote)
    invoice.is_emailed = False
    invoice.emailed_at = None
    # Reset status to DRAFT so it can be added to batch posting queue
    invoice.status = Invoice.Status.DRAFT
    invoice.save()
    
    messages.success(request, f"✓ Quote #{invoice.number} converted to Invoice. You can now send this invoice separately.")
    return redirect("invoices:invoice_detail", pk=pk)


@login_required
@require_POST
def reject_quote(request, pk):
    """Mark a quote as rejected."""
    from django.contrib import messages
    
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    if not invoice.is_quote:
        messages.error(request, "This is not a quote.")
        return redirect("invoices:invoice_detail", pk=pk)
    
    invoice.quote_status = "REJECTED"
    invoice.save()
    
    messages.success(request, f"✓ Quote #{invoice.number} marked as rejected and removed from list.")
    return redirect("invoices:invoice_list")


@login_required
@require_POST
def send_invoice(request, pk):
    """Send a DRAFT invoice or quote to the client."""
    from django.contrib import messages
    
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    if invoice.status != "DRAFT":
        messages.error(request, "Only DRAFT invoices/quotes can be sent.")
        return redirect("invoices:invoice_detail", pk=pk)
    
    # Send the invoice
    if email_invoice_to_client(invoice):
        doc_type = "Quote" if invoice.is_quote else "Invoice"
        messages.success(request, f"✓ {doc_type} #{invoice.number} sent to {invoice.client.email}")
    else:
        messages.error(request, "Failed to send invoice. Check email settings.")
    
    return redirect("invoices:dashboard")


@login_required
@setup_required
def client_statement(request, client_id):
    """
    Generate a year-end or custom date range statement for a client.
    Shows all recurring (queued) invoices and their payments with totals.
    """
    
    client = get_object_or_404(Client, id=client_id, user=request.user)
    
    # Get date range from query params (default to current year)
    year = int(request.GET.get('year', timezone.now().year))
    
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    # Get all RECURRING invoices for this client in the period
    # (invoices created from queued items with is_recurring=True)
    invoices = Invoice.objects.filter(
        user=request.user,
        client=client,
        invoice_date__range=[start_date, end_date],
        is_quote=False,
        # Link to items to find recurring ones
        billed_items__is_recurring=True
    ).distinct().order_by('invoice_date')
    
    # Get all payments for these invoices
    payments = Payment.objects.filter(
        invoice__user=request.user,
        invoice__client=client,
        invoice__in=invoices,
        created_at__date__range=[start_date, end_date]
    ).order_by('created_at')
    
    # Calculate totals
    total_invoiced = invoices.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    total_paid = payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    # Get outstanding balance on recurring invoices only
    all_recurring_outstanding = Invoice.objects.filter(
        user=request.user,
        client=client,
        is_quote=False,
        status__in=['PENDING', 'OVERDUE'],
        billed_items__is_recurring=True
    ).distinct().aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    
    # Get the queued items for this client to show the recurring pattern
    queued_items = Item.objects.filter(
        user=request.user,
        client=client,
        is_recurring=True,
        invoice__isnull=True
    ).order_by('description')
    
    context = {
        'client': client,
        'year': year,
        'start_date': start_date,
        'end_date': end_date,
        'invoices': invoices,
        'payments': payments,
        'queued_items': queued_items,
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'outstanding_balance': all_recurring_outstanding,
        'currency': request.user.profile.currency if hasattr(request.user, 'profile') else 'R',
    }
    
    return render(request, 'invoices/client_statement.html', context)
