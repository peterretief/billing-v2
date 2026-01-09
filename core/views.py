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
    # Ensure the profile exists for the logged-in user
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Files=request.FILES is added here in case you upload a company logo
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Company details and VAT settings updated.")
            return redirect('invoices:dashboard') 
    else:
        form = UserProfileForm(instance=profile)
        
    return render(request, 'core/profile_form.html', {
        'form': form,
        'profile': profile
    })


