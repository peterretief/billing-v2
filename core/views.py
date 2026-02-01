import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail  # <--- Added this
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import AdminUserCreationForm, AppInterestForm, UserProfileForm
from .models import UserProfile

User = get_user_model()

# --- Public Views ---

@login_required
@require_POST
def dismiss_onboarding(request):
    # HTMX sends this as a string "true"
    is_permanent = request.POST.get('permanent') == 'true'
    
    if is_permanent:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.show_onboarding_tips = False
        profile.save()
    
    # Return empty so HTMX removes the element immediately
    return HttpResponse("")


def contact_signup(request):
    """
    Handles the landing page contact form. 
    Replaces the standard signup with a lead-capture & vetting process.
    """
    submitted = False
    
    if request.method == 'POST':
        form = AppInterestForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            understanding = form.cleaned_data['understanding']
            
            # Construct the email body
            email_body = (
                f"New interest in the Billing App:\n\n"
                f"Name: {name}\n"
                f"Email: {email}\n\n"
                f"Understanding of the App:\n"
                f"{understanding}\n\n"
                f"--- End of Message ---"
            )
            
            try:
                send_mail(
                    subject=f"App Access Request: {name}",
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=['peter@diode.co.za'],
                    fail_silently=False,
                )
                # Toggle submitted to True to show the success preview
                submitted = True
                messages.success(request, "Your request has been sent to Peter.")
            except Exception:
                # Log the error if mail fails (useful for local debugging)
                messages.error(request,
                                "Unable to send email at this time. " \
                                "Please try again later.")
    else:
        form = AppInterestForm()

    return render(request, 'registration/signup_contact.html', {
        'form': form,
        'submitted': submitted
    })


def landing_page(request):
    """The main entry point: Handles the contact form or redirects if logged in."""
    
    # 1. Redirect if already logged in
    if request.user.is_authenticated:
        return redirect('invoices:dashboard')

    # 2. Check if we just 
    # redirected from a successful submission (prevents resend on refresh)
    submitted = request.GET.get('submitted') == 'true'

    if request.method == 'POST' and 'signup_request' in request.POST:
        form = AppInterestForm(request.POST)
        if form.is_valid():
            email_body = (
                f"New Access Request\n"
                f"Name: {form.cleaned_data['name']}\n"
                f"Email: {form.cleaned_data['email']}\n"
                f"Understanding: {form.cleaned_data['understanding']}"
            )
            try:
                send_mail(
                    subject="App Access Request",
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=['peter@diode.co.za'],
                )
                # Redirect to the same page with the success flag in the URL
                return redirect('/?submitted=true')
            except Exception:
                messages.error(request, "Mail server error.")
    else:
        # Handle Initial Load (GET request)
        form = AppInterestForm()

    return render(request, 'landing_page.html', {
        'form': form,
        'submitted': submitted
    })

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
            User.objects.create_user(
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
    form = UserProfileForm(request.POST or None, 
                           request.FILES or None, instance=profile)
    
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


