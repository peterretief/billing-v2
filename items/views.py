# items/views.py
from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from invoices.models import Invoice

from .forms import ItemForm
from .models import Item
from .services import import_recurring_to_invoices


class ItemListView(LoginRequiredMixin, ListView):
    model = Item
    template_name = "items/item_list.html"
    context_object_name = "one_off_items"

    def get_queryset(self):
        # TOP TABLE: Show only UNBILLED one-off items (not sent to invoice)
        # Items with is_billed=False OR invoice=NULL will show
        return Item.objects.filter(
            user=self.request.user,
            is_billed=False,  # Check is_billed status
            is_recurring=False,  # Only one-offs, not recurring templates
        ).order_by("-date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Pass 'today' allows the template to compare months for the green tick
        ctx["today"] = timezone.now()

        # BOTTOM TABLE: Persistent cycle items (Templates)
        ctx["queued_items"] = Item.objects.filter(user=self.request.user, is_recurring=True).order_by("-date", "-id")

        return ctx


# items/views.py


class ItemCreateView(LoginRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = "items/item_form.html"
    success_url = reverse_lazy("items:item_list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filter Clients
        form.fields["client"].queryset = form.fields["client"].queryset.filter(user=self.request.user)
        # Filter Billing Policies
        from billing_schedule.models import BillingPolicy

        form.fields["billing_policy"].queryset = BillingPolicy.objects.filter(user=self.request.user)
        return form


class ItemUpdateView(LoginRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = "items/item_form.html"
    success_url = reverse_lazy("items:item_list")

    def get_queryset(self):
        return Item.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filter Clients
        form.fields["client"].queryset = form.fields["client"].queryset.filter(user=self.request.user)
        # Filter Billing Policies
        from billing_schedule.models import BillingPolicy

        form.fields["billing_policy"].queryset = BillingPolicy.objects.filter(user=self.request.user)
        return form


class ItemDeleteView(LoginRequiredMixin, DeleteView):
    model = Item
    template_name = "items/item_confirm_delete.html"
    success_url = reverse_lazy("items:item_list")

    def get_queryset(self):
        return Item.objects.filter(user=self.request.user)


def generate_invoice_from_items(request):
    if request.method != "POST":
        return redirect("items:item_list")

    selected_ids = request.POST.getlist("selected_items")
    if not selected_ids:
        messages.warning(request, "Select items first.")
        return redirect("items:item_list")

    try:
        profile = request.user.profile
    except AttributeError:
        messages.error(request, "Please set up your Business Profile before generating invoices.")
        return redirect("core:edit_profile")

    with transaction.atomic():
        # Use manager method to check if items can be invoiced
        can_invoice, count_already_invoiced = Item.objects.can_be_invoiced(selected_ids)
        
        if not can_invoice:
            messages.error(
                request, 
                f"Cannot create invoice: {count_already_invoiced} selected item(s) are already linked to invoice(s). "
                "Items can only be invoiced once."
            )
            return redirect("items:item_list")
        
        items = (
            Item.objects.select_for_update()
            .filter(id__in=selected_ids, user=request.user, is_billed=False, is_recurring=False, invoice__isnull=True)
            .select_related("client")
        )

        if not items.exists():
            messages.info(request, "No unbilled items found for the selection.")
            return redirect("items:item_list")

        client_map = defaultdict(list)
        for item in items:
            client_map[item.client].append(item)

        flagged_count = 0
        for client, client_items in client_map.items():
            initial_tax_mode = Invoice.TaxMode.FULL if profile.is_vat_registered else Invoice.TaxMode.NONE

            invoice = Invoice.objects.create(
                user=request.user,
                client=client,
                due_date=timezone.now().date() + timedelta(days=client.payment_terms or 14),
                tax_mode=initial_tax_mode,
                status=Invoice.Status.DRAFT,
                billing_type=Invoice.BillingType.PRODUCT,
            )

            for item in client_items:
                item.is_billed = True
                item.invoice = invoice
                item.save()

            # Ensure this matches your model's calculation method
            # Usually invoice.sync_totals() or Invoice.objects.update_totals(invoice)
            invoice.sync_totals()
            invoice.save()

            # Add audit logging
            try:
                from core.models import BillingAuditLog, AuditHistory
                from core.utils import get_anomaly_status

                is_anomaly, comment, audit_context = get_anomaly_status(request.user, invoice)
                BillingAuditLog.objects.create(
                    user=request.user,
                    invoice=invoice,
                    is_anomaly=is_anomaly,
                    ai_comment=comment,
                    details={"total": float(invoice.total_amount), "source": "items_bulk_billing"},
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
                logger.error(f"Failed to create audit log for invoice {invoice.id}: {e}")
                # Don't fail the invoice creation just because audit failed

        messages.success(
            request,
            f"Generated {len(client_map)} invoice(s) as drafts."
            + (f" {flagged_count} flagged by audit." if flagged_count > 0 else ""),
        )

    return redirect("invoices:invoice_list")


@login_required
def trigger_billing(request):
    """
    Triggers the billing engine.
    Designed to work seamlessly with HTMX for a 'no-refresh' experience.
    """
    if request.method != "POST":
        return redirect("invoices:dashboard")

    try:
        # Run the engine
        new_invoice_ids = import_recurring_to_invoices(request.user)

        if new_invoice_ids:
            msg = f"Billing complete: {len(new_invoice_ids)} invoices generated and sent."
            msg_class = "success"
        else:
            msg = "Nothing to bill: All items are up to date for this month."
            msg_class = "info"

    except Exception as e:
        msg = f"System error: {str(e)}"
        msg_class = "danger"

    # HTMX Response: Returns a beautiful Bootstrap Alert partial
    if request.headers.get("HX-Request"):
        return HttpResponse(
            f'<div class="alert alert-{msg_class} alert-dismissible fade show border-0 shadow-sm" role="alert">'
            f'<i class="bi bi-info-circle-fill me-2"></i> {msg}'
            '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>'
            "</div>"
        )

    # Standard Redirect Fallback
    messages.add_message(request, getattr(messages, msg_class.upper()), msg)
    return redirect("invoices:dashboard")
