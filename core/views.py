import secrets
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm

from .models import UserProfile
from .forms import UserProfileForm, AdminUserCreationForm

User = get_user_model()

# --- Public Views ---

def landing_page(request):
    """Redirects authenticated users to dashboard, else shows landing."""
    if request.user.is_authenticated:
        return redirect('invoices:dashboard')
    return render(request, 'landing_page.html')

# --- Admin & User Management ---

@user_passes_test(lambda u: u.is_superuser)
def admin_create_user(request):
    """Admin tool to create a tenant user and trigger an email invite."""
    form = AdminUserCreationForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        username = form.cleaned_data['username']
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'A user with this email already exists.')
        else:
            # 1. Create user with a random usable password
            user = User.objects.create_user(
                username=username, 
                email=email, 
                password=secrets.token_urlsafe(32)
            )
            
            # 2. Send Invite via Password Reset system
            reset_form = PasswordResetForm(data={'email': email})
            if reset_form.is_valid():
                reset_form.save(
                    request=request,
                    use_https=request.is_secure(),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    subject_template_name='registration/password_reset_subject.txt',
                    email_template_name='registration/password_reset_email.html',
                )
            
            messages.success(request, f'User {username} created and invite sent.')
            return redirect('invoices:dashboard')

    return render(request, 'core/admin_create_user.html', {'form': form})

# --- Profile & Tenant Settings ---

@login_required
def edit_profile(request):
    """Updates UserProfile details and triggers HTMX UI refresh."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    form = UserProfileForm(request.POST or None, request.FILES or None, instance=profile)
    
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Business profile and tax settings updated.")
        
        # Prepare response with HTMX trigger for the breadcrumb setup list
        response = redirect('invoices:dashboard')
        response['HX-Trigger'] = 'profileUpdated'
        return response
        
    return render(request, 'core/profile_form.html', {
        'form': form, 
        'profile': profile
    })

@login_required
def update_profile(request):
    """Alias for edit_profile."""
    return edit_profile(request)