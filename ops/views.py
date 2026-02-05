
# Create your views here.
from django.db.models import Sum

from invoices.models import Invoice


def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    
    # Group totals by the user's currency setting
    # This assumes your UserProfile or User model has a 'currency' field
    revenue_by_currency = Invoice.objects.values(
        'user__userprofile__currency'
    ).annotate(
        total=Sum('total_amount')
    )
    
    context['revenue_summary'] = revenue_by_currency
    # ... rest of the queue logic ...
    return context