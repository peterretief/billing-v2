#import profile
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail  # <--- Added this
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_POST

#from .decorators import setup_required  # Your custom gatekeeper
from .forms import (
    AdminUserCreationForm,
    AppInterestForm,
    StaffCreateAndAddUserForm,
    UserGroupForm,
    UserProfileForm,
)
from .models import (
    GroupMember,
    OpsManager,  # Add OpsManager here
    UserGroup,
    UserProfile,
)

User = get_user_model()

# Define a helper check for reusability
def is_staff_or_admin(user):
    return user.is_active and (user.is_staff or user.is_superuser)


@login_required
@user_passes_test(is_staff_or_admin)
def tenant_report_detail(request, tenant_id):
    # 1. Use user__added_by as we discussed
    tenant_profile = get_object_or_404(
        UserProfile, 
        id=tenant_id, 
        user__added_by=request.user
    )
    
    # 2. Change 'date_created' to 'created_at' (or 'date_issued')
    # 3. Change 'invoice_number' to 'number' based on the "Choices" in your error
    invoices = tenant_profile.user.invoice_related.all().order_by('-created_at')
    
    total_invoiced = sum(inv.total_amount for inv in invoices)
    
    # Note: If 'amount_paid' is also missing from your Invoice model, 
    # use whatever field tracks payments, or calculate it from the payments relation.
    total_paid = sum(inv.total_paid for inv in invoices) # Assuming total_paid is a property
    total_outstanding = total_invoiced - total_paid

    return render(request, 'core/tenant_report_detail.html', {
        'tenant': tenant_profile,
        'invoices': invoices,
        'total_invoiced': total_invoiced,
        'total_outstanding': total_outstanding,
    })




@user_passes_test(lambda u: u.is_superuser)
def superuser_dashboard(request):
    """
    Displays the superuser-specific dashboard with app-wide analytics.
    """
    total_users = User.objects.count()
    recent_users = User.objects.order_by('-date_joined')[:5]

    all_invoices = Invoice.objects.all()
    
    total_revenue = all_invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    # Calculate total outstanding by summing up balance_due of all invoices
    total_outstanding = sum(invoice.balance_due for invoice in all_invoices)

    context = {
        'total_users': total_users,
        'recent_users': recent_users,
        'total_revenue': total_revenue,
        'total_outstanding': total_outstanding,
    }
    return render(request, 'admin/index.html', context)

@login_required
@user_passes_test(is_staff_or_admin)
def portfolio_summary(request):
    if not request.user.is_staff:
        return redirect('invoices:dashboard')

    manager = OpsManager.objects.get(pk=request.user.pk)
    
    # 1. Get all profiles in the portfolio
    tenants = manager.get_portfolio().select_related('user')

    currency_groups = {}
    
    for t in tenants:
        # 2. Get all invoices for THIS specific tenant
        # We use .filter() directly to avoid any BigAutoField lookup issues
        tenant_invoices = t.user.invoice_related.all()
        
        # 3. Sum them up manually
        # Replace 'total_amount' and 'amount_paid' with your actual field names if different
        rev = sum(inv.total_amount for inv in tenant_invoices)
        
        # If 'balance_due' is a property, we use it here!
        out = sum(inv.balance_due for inv in tenant_invoices)
        
        t.total_revenue = rev
        t.total_outstanding = out
        
        curr = t.currency
        if curr not in currency_groups:
            currency_groups[curr] = {'revenue': 0, 'outstanding': 0}
        
        currency_groups[curr]['revenue'] += rev
        currency_groups[curr]['outstanding'] += out

    return render(request, 'core/portfolio_summary.html', {
        'tenants': tenants,
        'stats': currency_groups.items(),
    })

@login_required
@user_passes_test(is_staff_or_admin)
def view_tenant_readonly(request, tenant_id):
    """
    Allows a manager to view a specific tenant's dashboard without edit rights.
    """
    # Fetch the tenant user, ensuring they were added by the current logged-in manager
    tenant_user = get_object_or_404(User, id=tenant_id, added_by=request.user)
    
    # Show the standard dashboard, but pass the read_only flag
    return render(request, 'invoices/dashboard.html', {
        'target_tenant': tenant_user.profile,
        'read_only': True,
        'is_manager_view': True
    })
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

@login_required
def initial_setup(request):
    # 1. Always fetch the profile first
    user_profile = request.user.profile 

    if request.method == 'POST':
        dropdown_val = request.POST.get('currency_dropdown')
        custom_val = request.POST.get('currency_custom')
        # Check for the VAT switch
        is_vat = request.POST.get('is_vat') == 'on'

        if dropdown_val == 'OTHER' and custom_val:
            user_profile.currency = custom_val[:3]
        else:
            user_profile.currency = dropdown_val

        user_profile.is_vat_registered = is_vat
        user_profile.initial_setup_complete = True
        user_profile.save()
        
        return redirect('invoices:dashboard')

    # 2. THE MISSING PIECE: Handle the GET request (showing the form)
    return render(request, 'core/initial_setup.html', {'profile': user_profile})

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


@login_required
@user_passes_test(is_staff_or_admin)
def manager_create_tenant(request):
    """
    Allows an OpsManager to create a new tenant user, automatically assigning
    the tenant to their portfolio.
    """
    if not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to access this page.")

    form = AdminUserCreationForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        username = form.cleaned_data['username']
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'A user with this email already exists.')
        else:
            # 1. Create user with a random password AND link to manager
            User.objects.create_user(
                username=username, 
                email=email, 
                password=secrets.token_urlsafe(32),
                added_by=request.user  # This links the tenant to the manager
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
            
            messages.success(request, f'Tenant {username} created and invite sent.')
            return redirect('core:portfolio_summary') # Redirect back to portfolio

    return render(request, 'core/manager_create_tenant.html', {'form': form})


# --- Group Management Views (Staff Only) ---

@user_passes_test(lambda u: u.is_staff)
def staff_groups_list(request):
    """
    List all groups managed by the current staff member.
    """
    groups = UserGroup.objects.filter(manager=request.user)
    context = {
        'groups': groups,
    }
    return render(request, 'core/staff_groups_list.html', context)


@user_passes_test(lambda u: u.is_staff)
def staff_group_create(request):
    """
    Add a test user to the staff user's group.
    Group is auto-created with staff user's name if it doesn't exist.
    """
    form = UserGroupForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        # Get or create group for staff user
        group, created = UserGroup.objects.get_or_create(
            manager=request.user,
            defaults={'name': f"{request.user.first_name or request.user.username}'s Group"}
        )
        
        email = form.cleaned_data['add_user_email']
        username = form.cleaned_data['add_user_username']
        
        # Create the new user
        new_user = User.objects.create_user(
            username=username,
            email=email,
            password=secrets.token_urlsafe(32)
        )
        
        # Add user to group with TENANT role
        member = GroupMember.objects.create(
            group=group,
            user=new_user,
            role='TENANT',
            added_by=request.user
        )
        
        # Send welcome email
        try:
            # Generate password reset token and URL
            uid = urlsafe_base64_encode(force_bytes(new_user.pk))
            token = default_token_generator.make_token(new_user)
            reset_url = request.build_absolute_uri(
                reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
            )
            
            send_mail(
                subject=f"Welcome to {group.name}",
                message=(
                    f"Hello {new_user.first_name or new_user.username},\n\n"
                    f"You have been added to the group '{group.name}'.\n\n"
                    f"Click the link below to set your password:\n"
                    f"{reset_url}\n\n"
                    f"Best regards"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[new_user.email],
                fail_silently=False,
            )
        except Exception:
            messages.warning(request, 'User created but welcome email could not be sent.')
        
        group_status = "created" if created else "updated"
        messages.success(request, f'Group "{group.name}" {group_status} and user {username} added.')
        return redirect('core:staff_groups_list')
    
    context = {
        'form': form,
        'page_title': 'Add User',
    }
    return render(request, 'core/staff_group_form.html', context)


@user_passes_test(lambda u: u.is_staff)
def staff_group_detail(request, group_id):
    """
    View group details and members (staff can only view their own groups).
    """
    group = get_object_or_404(UserGroup, id=group_id, manager=request.user)
    members = group.members.all()
    
    context = {
        'group': group,
        'members': members,
    }
    return render(request, 'core/staff_group_detail.html', context)


@user_passes_test(lambda u: u.is_staff)
def staff_add_group_member(request, group_id):
    """
    Add a member to a group (staff can only add to their own groups).
    All added users get TENANT role.
    """
    group = get_object_or_404(UserGroup, id=group_id, manager=request.user)
    form = StaffCreateAndAddUserForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        username = form.cleaned_data['username']
        
        # Create the new user with a random password
        new_user = User.objects.create_user(
            username=username,
            email=email,
            password=secrets.token_urlsafe(32)
        )
        
        # Add user to group with TENANT role
        member = GroupMember.objects.create(
            group=group,
            user=new_user,
            role='TENANT',
            added_by=request.user
        )
        
        # Send welcome email to the new user
        try:
            # Generate password reset token and URL
            uid = urlsafe_base64_encode(force_bytes(new_user.pk))
            token = default_token_generator.make_token(new_user)
            reset_url = request.build_absolute_uri(
                reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
            )
            
            send_mail(
                subject=f"Welcome to {group.name}",
                message=(
                    f"Hello {new_user.first_name or new_user.username},\n\n"
                    f"You have been added to the group '{group.name}'.\n\n"
                    f"Click the link below to set your password:\n"
                    f"{reset_url}\n\n"
                    f"Best regards"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[new_user.email],
                fail_silently=False,
            )
        except Exception:
            messages.warning(request, 'User created but welcome email could not be sent.')
        
        messages.success(request, f'User {username} created and added to group {group.name}.')
        return redirect('core:staff_group_detail', group_id=group.id)
    
    context = {
        'form': form,
        'group': group,
        'page_title': f'Add Member to {group.name}',
    }
    return render(request, 'core/staff_add_member_form.html', context)


@user_passes_test(lambda u: u.is_staff)
@require_POST
def staff_remove_group_member(request, group_id, member_id):
    """
    Remove a member from a group (staff can only remove from their own groups).
    """
    group = get_object_or_404(UserGroup, id=group_id, manager=request.user)
    member = get_object_or_404(GroupMember, id=member_id, group=group)
    username = member.user.username
    member.delete()
    messages.success(request, f'User {username} removed from group {group.name}.')
    return redirect('core:staff_group_detail', group_id=group.id)


