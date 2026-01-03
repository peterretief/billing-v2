from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView
from django.contrib import messages
from django.db.models import Sum, Q

from .models import Client
from .forms import ClientForm
from invoices.models import Invoice


# --- 1. LIST VIEW (Using our new Manager) ---
class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'

    def get_queryset(self):
        # This uses the smart manager method we wrote earlier!
        return Client.objects.filter(user=self.request.user).with_balances()

# --- 2. EDIT/ADD VIEW (Combined Function) ---
@login_required
def client_edit(request, pk=None):
    if pk:
        client = get_object_or_404(Client, pk=pk, user=request.user)
    else:
        client = Client(user=request.user)

    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f"Client '{client.name}' saved.")
            return redirect('clients:client_list')
    else:
        form = ClientForm(instance=client)
    
    return render(request, 'clients/client_form.html', {'form': form, 'is_edit': bool(pk)})



# clients/views.py
from invoices.utils import format_currency

# --- 3. STATEMENT VIEW (Ledger Style) ---

@login_required
def client_statement(request, pk):
    client = get_object_or_404(Client, pk=pk, user=request.user)
    invoices = Invoice.objects.filter(client=client).order_by('-date_issued')
    
    raw_stats = invoices.aggregate(
        total_billed=Sum('total_amount'),
        paid=Sum('total_amount', filter=Q(status='PAID')),
        unpaid=Sum('total_amount', filter=Q(status__in=['PENDING', 'OVERDUE', 'DRAFT']))
    )

    # Clean the decimals using the utility
    stats = {
        'total_billed': format_currency(raw_stats['total_billed']),
        'paid': format_currency(raw_stats['paid']),
        'unpaid': format_currency(raw_stats['unpaid']),
    }

    return render(request, 'clients/client_statement.html', {
        'client': client,
        'invoices': invoices,
        'stats': stats,
    })

   
class ClientDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'clients/client_detail.html'
    context_object_name = 'client'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Use the related name from your Invoice model's ForeignKey to Client
        context['invoices'] = self.object.invoices.all().order_by('-date_issued')
        return context    