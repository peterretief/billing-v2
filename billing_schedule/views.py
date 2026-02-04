from django.shortcuts import get_object_or_404, redirect, render

from .forms import BillingPolicyForm
from .models import BillingPolicy


def delete_policy(request, pk):
    # Only find the policy if it belongs to the current user
    policy = get_object_or_404(BillingPolicy, pk=pk, user=request.user)
    
    if request.method == "POST":
        policy.delete()
        return redirect('billing_schedule:policy_list')
    
    # If they just navigate to the URL, show a confirmation page
    return render(request, 'billing_schedule/policy_confirm_delete.html', {'policy': policy})

def policy_list(request):
    # Only show policies belonging to the current user
    policies = BillingPolicy.objects.filter(user=request.user)
    return render(request, 'billing_schedule/policy_list.html', {'policies': policies})


def create_policy(request):
    if request.method == "POST":
        form = BillingPolicyForm(request.POST)
        if form.is_valid():
            policy = form.save(commit=False)
            policy.user = request.user  # Assign the user
            policy.save()
            return redirect('billing_schedule:policy_list')
    else:
        form = BillingPolicyForm()
    return render(request, 'billing_schedule/policy_form.html', {'form': form})

def edit_policy(request, pk):
    policy = get_object_or_404(BillingPolicy, pk=pk, user=request.user)
    if request.method == "POST":
        form = BillingPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            return redirect('billing_schedule:policy_list')
    else:
        form = BillingPolicyForm(instance=policy)
    return render(request, 'billing_schedule/policy_form.html', {'form': form})