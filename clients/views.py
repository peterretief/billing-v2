from django.db.models import Sum, F, Q, ExpressionWrapper, DecimalField
from django.urls import reverse
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Client


from django.views.generic.edit import CreateView
from .models import Client

class ClientCreateView(LoginRequiredMixin, CreateView):
    model = Client
    fields = ['name', 'email', 'phone', 'address', 'vat_number']
    template_name = 'clients/client_form.html'
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('clients:client_list')

# Helper for calculation to keep the code DRY (Don't Repeat Yourself)
def get_total_calculation():
    """Returns the logic to multiply qty by price across invoice items."""
    return ExpressionWrapper(
        F('invoice__items__quantity') * F('invoice__items__unit_price'),
        output_field=DecimalField()
    )

# 1. CLIENT LIST VIEW
# Shows all clients + their specific outstanding balances
class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'


# clients/views.py

def get_queryset(self):
    # Multi-tenancy: Only show clients belonging to the user
    queryset = Client.objects.filter(user=self.request.user)

    # Annotate: Use 'invoices' (plural) to match your model's relationship field
    queryset = queryset.annotate(
        outstanding_balance=Sum(
            get_total_calculation(),
            filter=Q(invoices__status='unpaid') # Change 'invoice' to 'invoices'
        )
    ).order_by('-outstanding_balance')
    
    return queryset


# 2. CLIENT DETAIL VIEW
# Shows one client's info + their full invoice history + lifetime stats
class ClientDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'clients/client_detail.html'
    context_object_name = 'client'

    def get_queryset(self):
        # Security: Prevent users from viewing clients they don't own
        return Client.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object

        # Fetch all invoices for this client (newest first)
        invoices = client.invoices.all().order_by('-date_issued')
        
        # Calculate summary totals for the top of the detail page
        # Note: We use 'items__' here because we are starting from the client's invoices
        stats = invoices.aggregate(
            total_lifetime=Sum(
                ExpressionWrapper(
                    F('items__quantity') * F('items__unit_price'),
                    output_field=DecimalField()
                )
            ),
            total_outstanding=Sum(
                ExpressionWrapper(
                    F('items__quantity') * F('items__unit_price'),
                    output_field=DecimalField()
                ),
                filter=Q(status='unpaid')
            )
        )

        context['invoices'] = invoices
        context['total_lifetime'] = stats['total_lifetime'] or 0
        context['total_outstanding'] = stats['total_outstanding'] or 0
        
        return context