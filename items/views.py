# items/views.py
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from .models import Item
from .forms import ItemForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.db import transaction
from collections import defaultdict
from invoices.models import Invoice, InvoiceItem
from django.utils import timezone
from datetime import timedelta


class ItemListView(LoginRequiredMixin, ListView):
    model = Item
    template_name = 'items/item_list.html'
    context_object_name = 'items'

    def get_queryset(self):
        return Item.objects.filter(user=self.request.user, is_billed=False)

class ItemCreateView(LoginRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = 'items/item_form.html'
    success_url = reverse_lazy('items:item_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filter client dropdown to only show clients added by this user
        form.fields['client'].queryset = form.fields['client'].queryset.filter(user=self.request.user)
        return form

class ItemUpdateView(LoginRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = 'items/item_form.html'
    success_url = reverse_lazy('items:item_list')

    def get_queryset(self):
        return Item.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filter client dropdown to only show clients added by this user
        form.fields['client'].queryset = form.fields['client'].queryset.filter(user=self.request.user)
        return form

class ItemDeleteView(LoginRequiredMixin, DeleteView):
    model = Item
    template_name = 'items/item_confirm_delete.html'
    success_url = reverse_lazy('items:item_list')

    def get_queryset(self):
        return Item.objects.filter(user=self.request.user)


def generate_invoice_from_items(request):
    if request.method != 'POST':
        return redirect('items:item_list')

    selected_ids = request.POST.getlist('selected_items')
    if not selected_ids:
        messages.warning(request, "Select items first.")
        return redirect('items:item_list')

    try:
        profile = request.user.profile
    except AttributeError:
        messages.error(request, "Please set up your Business Profile before generating invoices.")
        return redirect('core:edit_profile')

    with transaction.atomic():
        items = Item.objects.select_for_update().filter(
            id__in=selected_ids,
            user=request.user,
            is_billed=False
        ).select_related('client')

        if not items.exists():
            messages.info(request, "No unbilled items found for the selection.")
            return redirect('items:item_list')

        client_map = defaultdict(list)
        for item in items:
            client_map[item.client].append(item)

        for client, client_items in client_map.items():
            initial_tax_mode = Invoice.TaxMode.FULL if profile.is_vat_registered else Invoice.TaxMode.NONE

            invoice = Invoice.objects.create(
                user=request.user,
                client=client,
                due_date=timezone.now().date() + timedelta(days=client.payment_terms or 14),
                tax_mode=initial_tax_mode,
                status=Invoice.Status.DRAFT,
                billing_type=Invoice.BillingType.PRODUCT
            )

            for item in client_items:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    is_taxable=profile.is_vat_registered
                )
                item.is_billed = True
                item.invoice = invoice
                item.save()

            invoice.sync_totals()
            invoice.save()

        messages.success(request, f"Generated {len(client_map)} invoice(s) as drafts.")

    return redirect('invoices:invoice_list')