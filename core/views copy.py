from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpRequest
from django.contrib import messages
from django.template.loader import render_to_string
from .models import UserProfile, User
from .forms import UserProfileForm, AdminUserCreationForm
from django.contrib.auth.forms import PasswordResetForm


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('invoices:dashboard')
    return render(request, 'landing_page.html')

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
            
            if User.objects.filter(username=username).exists():
                messages.error(request, 'A user with this username already exists.')
                return render(request, 'core/admin_create_user.html', {'form': form})

            # Create the user with an unusable password
            user = User.objects.create_user(username=username, email=email)
            user.set_unusable_password()
            user.save()

            # --- Send Password Reset Email ---
            # We are using Django's built-in PasswordResetForm to send the email.
            password_reset_form = PasswordResetForm(data={'email': user.email})
            if password_reset_form.is_valid():
                # This form needs a proper request object to build the password reset URLs
                # We will fake a request object for this purpose
                fake_request = HttpRequest()
                fake_request.method = 'POST'
                fake_request.META['SERVER_NAME'] = request.META['SERVER_NAME']
                fake_request.META['SERVER_PORT'] = request.META['SERVER_PORT']
                
                password_reset_form.save(
                    request=fake_request,
                    use_https=request.is_secure(),
                    email_template_name='registration/password_reset_email.html',
                    subject_template_name='registration/password_reset_subject.txt'
                )

            messages.success(request, f'User {username} created. A password reset link has been sent to {email}.')
            return redirect('invoices:dashboard')
    else:
        form = AdminUserCreationForm()

    return render(request, 'core/admin_create_user.html', {'form': form})


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


