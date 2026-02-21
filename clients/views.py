from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView

from invoices.models import Invoice

# ... (your existing imports) ...
from timesheets.forms import TimesheetEntryForm

from .forms import ClientForm
from .models import Client

# views.py


class ClientDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'clients/client_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object
        
        # Pulling the related data for the specific client
        context['invoices'] = client.invoices.all().order_by('-date_issued')
        context['unbilled_timesheets'] = client.timesheets.filter(is_billed=False)
        
        # Pre-fill the form with this client and their default rate
        context['timesheet_form'] = TimesheetEntryForm(initial={
            'client': client,
            'hourly_rate': client.default_hourly_rate  # Using the new field we added
        })
        return context



# --- 1. LIST VIEW (Using our new Manager) ---
class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'

    paginate_by = 20

    def get_queryset(self):
        qs = Client.objects.filter(user=self.request.user).with_balances()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(client_code__icontains=q) |
                Q(email__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        return context

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

   
