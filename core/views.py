from django.shortcuts import render
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.template.loader import render_to_string
from .models import UserProfile
from .forms import UserProfileForm
# Create your views here.
# core/views.py


# Add this alias so 'update_profile' works too
@login_required
def update_profile(request):
    return edit_profile(request)

@login_required
def edit_profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            # This message will pop up on the Dashboard after redirecting
            messages.success(request, "Company details updated successfully.")
            return redirect('invoices:dashboard') 
    else:
        form = UserProfileForm(instance=profile)
        
    return render(request, 'core/profile_form.html', {'form': form})