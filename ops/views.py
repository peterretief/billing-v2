import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import F, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.generic import TemplateView

# Import models from your apps
from invoices.models import Invoice

from .forms import TenantInviteForm
from .models import BillingBatch, OpsAssignment
from .services import create_and_invite_tenant  # Using the new service

logger = logging.getLogger(__name__)
User = get_user_model()


def invite_tenant_view(request):
    if request.method == 'POST':
        form = TenantInviteForm(request.POST)
        if form.is_valid():
            try:
                # Use the new, more descriptive service function
                new_user = create_and_invite_tenant(
                    request=request,
                    ops_user=request.user,
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    company_name=form.cleaned_data['company_name'],
                    # Pass extra data which the service will handle
                    currency=form.cleaned_data['currency'],
                    vat_number=form.cleaned_data.get('vat_number', ''),
                    vat_rate=form.cleaned_data.get('vat_rate', 20.00)
                )
                messages.success(request, f"Invite sent successfully to {new_user.email}.")
                return redirect('ops:dashboard')
            except ValueError as e:
                # Handle the case where the user already exists
                messages.error(request, str(e))
            except Exception as e:
                # If the service layer raises any other exception, show it
                logger.error(
                    f"Tenant invitation failed for {form.cleaned_data['email']}. "
                    f"Error: {str(e)}", exc_info=True
                )
                messages.error(
                    request,
                    "An unexpected error occurred. Please check the logs or contact support."
                )

    else:
        form = TenantInviteForm()

    return render(request, 'ops/invite_tenant.html', {'form': form})

class OpsDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'ops/dashboard.html'

    def test_func(self):
        """
        Only allow Superusers or users specifically assigned as Ops
        (Staff or Group-based).
        """
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.now().date()

        # Get search query from URL: /ops/?q=peter
        search_query = self.request.GET.get('q', '')

        # --- STEP 1: IDENTIFY ASSIGNED TENANTS ---
        if user.is_superuser:
            # Uber User sees everyone
            assigned_tenants = User.objects.all()
        else:
            # Ops Manager only sees their assigned tenants via the bridge model
            assigned_tenant_ids = OpsAssignment.objects.filter(
                ops_user=user
            ).values_list('tenant_id', flat=True)
            assigned_tenants = User.objects.filter(id__in=assigned_tenant_ids)

        # --- STEP 2: APPLY SEARCH FILTER ---
        if search_query:
            assigned_tenants = assigned_tenants.filter(
                Q(username__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(profile__company_name__icontains=search_query)
            ).distinct()

        # Get the final list of IDs for financial/batch filtering
        # This ensures stats reflect the searched list if desired,
        # but here we use it to scope the metrics to the Op's permissions.
        final_tenant_ids = assigned_tenants.values_list('id', flat=True)

        # --- STEP 3: FINANCIAL REPORTING (BY CURRENCY) ---
        revenue_by_currency = Invoice.objects.filter(
            user_id__in=final_tenant_ids
        ).values(
            currency=F('user__profile__currency')
        ).annotate(
            total=Sum('total_amount')
        ).order_by('currency')

        # --- STEP 4: BATCH PROGRESS (FOR THE PROGRESS BAR) ---
        batch_qs = BillingBatch.objects.filter(
            user_id__in=final_tenant_ids,
            scheduled_date=today
        )

        total_in_batch = batch_qs.count()
        done_in_batch = batch_qs.filter(is_processed=True).count()

        # --- STEP 5: ASSEMBLE CONTEXT ---
        context.update({
            'revenue_summary': revenue_by_currency,
            'system_invoice_count': Invoice.objects.filter(user_id__in=final_tenant_ids).count(),
            'batch_stats': {
                'total': total_in_batch,
                'done': done_in_batch,
                'percentage': int((done_in_batch / total_in_batch) * 100) if total_in_batch > 0 else 0
            },
            # We limit the list to 20 for the dashboard to keep it fast
            'managed_users': assigned_tenants.select_related('profile')[:20],
            'search_query': search_query,
        })

        return context