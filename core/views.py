from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.sites.shortcuts import get_current_site

from .models import UserProfile
from .forms import UserProfileForm, AdminUserCreationForm

User = get_user_model()

# --- Landing & Dashboard ---

def landing_page(request):
    """Simple landing page that redirects logged-in users."""
    if request.user.is_authenticated:
        return redirect('invoices:dashboard')
    return render(request, 'landing_page.html')

# --- Admin User Creation & Invite ---



import secrets # Standard Python library for random strings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.conf import settings

User = get_user_model()

@user_passes_test(lambda u: u.is_superuser)
def admin_create_user(request):
    if request.method == 'POST':
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email = form.cleaned_data['email']
            
            if User.objects.filter(email=email).exists():
                messages.error(request, 'A user with this email already exists.')
                return render(request, 'core/admin_create_user.html', {'form': form})

            # 1. Create the user with a RANDOM USABLE password
            # This is the "Key" that allows PasswordResetForm to work
            temp_password = secrets.token_urlsafe(32)
            user = User.objects.create_user(
                username=username, 
                email=email, 
                password=temp_password
            )
            user.is_active = True # Must be active for the form to work
            user.save()

            # 2. Trigger the invitation via PasswordResetForm
            reset_form = PasswordResetForm(data={'email': user.email})
            if reset_form.is_valid():
                # We use the actual request to get the domain (peterretief.org)
                reset_form.save(
                    request=request,
                    use_https=request.is_secure(),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    subject_template_name='registration/password_reset_subject.txt',
                    email_template_name='registration/password_reset_email.html',
                )

            messages.success(request, f'User {username} created and invite sent to {email}.')
            return redirect('invoices:dashboard')
    else:
        form = AdminUserCreationForm()

    return render(request, 'core/admin_create_user.html', {'form': form})


# --- Profile Management ---

@login_required
def update_profile(request):
    """Alias for edit_profile."""
    return edit_profile(request)

@login_required
def edit_profile(request):
    """
    Manages the UserProfile (business details, VAT, etc.) 
    for the logged-in tenant.
    """
    # get_or_create ensures no DoesNotExist errors if profile was missed at signup
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Added request.FILES for the business logo upload
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Business profile and tax settings updated.")
            return redirect('invoices:dashboard') 
    else:
        form = UserProfileForm(instance=profile)
        
    return render(request, 'core/profile_form.html', {
        'form': form,
        'profile': profile
    })