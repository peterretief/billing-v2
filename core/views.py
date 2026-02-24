# import profile
import json
import logging
import secrets
from collections import defaultdict

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from invoices.models import Invoice, InvoiceEmailStatusLog

from .forms import (
    AdminUserCreationForm,
    AppInterestForm,
    AuditSettingsForm,
    StaffCreateAndAddUserForm,
    UserGroupForm,
    UserProfileForm,
)
from .models import (
    GroupMember,
    OpsManager,
    UserGroup,
    UserProfile,
)

User = get_user_model()
logger = logging.getLogger(__name__)

# --- Helper Logic for Email Tracking ---


def get_grouped_logs(user, invoice_id=None):
    """
    Helper to fetch and group logs.
    If invoice_id is provided, it only returns data for that one invoice.
    """
    logs_query = InvoiceEmailStatusLog.objects.filter(user=user).select_related("invoice")

    if invoice_id:
        logs_query = logs_query.filter(invoice_id=invoice_id)

    # Define status priority (higher index = higher priority)
    status_priority = {
        "DELIVERED": 3,
        "SENT": 2,
        "REQUEST": 1,
        # Add more statuses as needed
    }

    grouped_logs = defaultdict(list)
    for log in logs_query:
        grouped_logs[log.invoice].append(log)

    # For each invoice, sort logs by status priority (desc), then by created_at (desc)
    for invoice, logs in grouped_logs.items():
        logs.sort(key=lambda l: (status_priority.get(l.status.upper(), 0), l.created_at), reverse=True)

    return dict(grouped_logs)


# --- Email Status Views ---


@login_required
def sync_invoice_status(request, invoice_id):
    last_log = (
        InvoiceEmailStatusLog.objects.filter(invoice_id=invoice_id, user=request.user).order_by("-created_at").first()
    )

    if not last_log or not last_log.brevo_message_id:
        return render(
            request,
            "partials/email_status_rows.html",
            {"grouped_data": get_grouped_logs(request.user, invoice_id=invoice_id)},
        )

    msg_id = last_log.brevo_message_id.strip("<>")
    api_url = f"https://api.brevo.com/v3/smtp/statistics/events?messageId={msg_id}&limit=50"
    headers = {"accept": "application/json", "api-key": settings.BREVO_API_KEY}

    try:
        response = requests.get(api_url, headers=headers, timeout=5)
        if response.status_code == 200:
            events = response.json().get("events", [])

            # Get all statuses we've already logged to avoid duplicates
            existing = set(
                InvoiceEmailStatusLog.objects.filter(invoice_id=invoice_id, user=request.user).values_list(
                    "status", "created_at"
                )
            )

            to_create = []
            for event in events:
                new_status = event.get("event")
                # Brevo uses 'date' field in ISO format on events
                event_time = event.get("date")
                if new_status and (new_status, event_time) not in existing:
                    to_create.append(
                        InvoiceEmailStatusLog(
                            invoice=last_log.invoice,
                            user=request.user,
                            brevo_message_id=last_log.brevo_message_id,
                            status=new_status,
                            # Pass created_at if your model allows it, otherwise omit
                        )
                    )

            if to_create:
                InvoiceEmailStatusLog.objects.bulk_create(to_create, ignore_conflicts=True)

    except Exception as e:
        logger.error(f"Brevo Sync Error: {e}")

    return render(
        request,
        "partials/email_status_rows.html",
        {"grouped_data": get_grouped_logs(request.user, invoice_id=invoice_id)},
    )


@login_required
def api_invoice_delivery_statuses(request):
    """API endpoint to fetch delivery statuses for multiple invoices (JSON)."""
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"API called - Referer: {request.META.get('HTTP_REFERER', 'N/A')} | User-Agent snippet: {request.META.get('HTTP_USER_AGENT', 'N/A')[:80]}"
    )

    # Get invoice IDs from query string or POST body
    invoice_ids = request.GET.getlist("ids")

    if not invoice_ids and request.method == "POST":
        try:
            data = json.loads(request.body)
            invoice_ids = data.get("ids", [])
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not invoice_ids:
        return JsonResponse({"error": "No invoice IDs provided"}, status=400)

    # Handle comma-separated IDs (if single parameter with commas)
    if len(invoice_ids) == 1 and "," in invoice_ids[0]:
        invoice_ids = invoice_ids[0].split(",")

    # Convert to integers and filter out invalid ones
    try:
        invoice_ids = [int(id_str.strip()) for id_str in invoice_ids if id_str.strip().isdigit()]
    except (ValueError, AttributeError):
        return JsonResponse({"error": "Invalid invoice IDs format"}, status=400)

    if not invoice_ids:
        return JsonResponse({"error": "No valid invoice IDs"}, status=400)

    # Fetch invoices for this user
    invoices = Invoice.objects.filter(user=request.user, id__in=invoice_ids).values_list("id", flat=True)

    # Build response with delivery statuses
    status_map = {}
    for invoice_id in invoices:
        invoice = Invoice.objects.get(id=invoice_id, user=request.user)
        status_map[str(invoice_id)] = invoice.get_latest_delivery_status() or "unknown"

    return JsonResponse({"statuses": status_map})


@login_required
def email_status_view(request):
    """Main view for the full delivery tracking page."""
    return render(request, "core/email_status.html", {"grouped_data": get_grouped_logs(request.user)})


@login_required
def email_status_rows(request):
    """Partial view for HTMX refreshing of rows."""
    invoice_id = request.GET.get("invoice_id")
    return render(
        request,
        "partials/email_status_rows.html",
        {"grouped_data": get_grouped_logs(request.user, invoice_id=invoice_id)},
    )


@csrf_exempt
def brevo_webhook(request):
    """
    Handle Brevo email event webhooks (sent, delivered, bounce, complaint, etc.)
    Brevo sends events in format: {"event": "sent", "message-id": "<id>", ...}
    """
    if request.method == "POST":
        import logging

        logger = logging.getLogger(__name__)

        try:
            # Log raw webhook data
            raw_body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
            logger.info(f"Brevo webhook received: {raw_body[:500]}")

            data = json.loads(raw_body)

            # Extract message ID - Brevo can send it in different formats
            message_id = data.get("message-id") or data.get("messageId") or data.get("id")
            if not message_id:
                logger.error(f"No message ID found in webhook data: {data}")
                return HttpResponse('{"error": "No message-id found"}', status=400)

            # Clean message ID (remove angle brackets if present)
            message_id = message_id.strip("<> ")
            logger.debug(f"Cleaned message_id: {message_id}")

            # Extract status/event
            new_status = data.get("event") or data.get("status")
            if not new_status:
                logger.error(f"No event/status found in webhook data: {data}")
                return HttpResponse('{"error": "No event found"}', status=400)

            logger.info(f"Processing Brevo webhook: message_id={message_id}, status={new_status}")

            # Find the invoice email log by message ID using exact match first, then fallback to substring
            parent = InvoiceEmailStatusLog._base_manager.filter(brevo_message_id__iexact=message_id).first()

            # If exact match fails, try substring match
            if not parent:
                logger.debug(f"Exact match failed, trying substring match for: {message_id}")
                parent = InvoiceEmailStatusLog._base_manager.filter(brevo_message_id__icontains=message_id).first()

            if parent:
                logger.info(f"Found parent log {parent.id}, creating new status log: {new_status}")
                new_log = InvoiceEmailStatusLog.objects.create(
                    invoice=parent.invoice,
                    user=parent.user,
                    brevo_message_id=parent.brevo_message_id,
                    status=new_status,
                )
                logger.info(f"Created new log {new_log.id} with status {new_status}")
                return HttpResponse("CURL_SUCCESS", status=201)
            else:
                logger.warning(
                    f"No parent log found for message_id: {message_id}. This email may not have been logged initially."
                )
                # Check if this is a brand new email that hasn't been logged yet
                logger.debug("Searching database for similar message IDs...")
                similar = InvoiceEmailStatusLog._base_manager.filter(
                    brevo_message_id__icontains=message_id[:15]
                ).values_list("brevo_message_id", flat=True)[:5]
                if similar:
                    logger.debug(f"Similar IDs in database: {similar}")
                return HttpResponse(f'{{"error": "Message {message_id} not found"}}', status=404)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse webhook JSON: {e}, body: {request.body[:200]}")
            return HttpResponse(f'{{"error": "Invalid JSON: {str(e)}"}}', status=400)
        except Exception as e:
            import traceback

            logger.error(f"Webhook error: {e}\n{traceback.format_exc()}")
            return HttpResponse(f'{{"error": "{str(e)}"}}', status=500)

    return HttpResponse('{"error": "Method not allowed"}', status=405)


# --- Portfolio & Management Views ---


def is_staff_or_admin(user):
    return user.is_active and (user.is_staff or user.is_superuser)


@login_required
@user_passes_test(is_staff_or_admin)
def tenant_report_detail(request, tenant_id):
    tenant_profile = get_object_or_404(UserProfile, id=tenant_id, user__added_by=request.user)
    invoices = tenant_profile.user.invoice_related.all().order_by("-created_at")
    total_invoiced = sum(inv.total_amount for inv in invoices)
    total_paid = sum(inv.total_paid for inv in invoices)
    total_outstanding = total_invoiced - total_paid

    return render(
        request,
        "core/tenant_report_detail.html",
        {
            "tenant": tenant_profile,
            "invoices": invoices,
            "total_invoiced": total_invoiced,
            "total_outstanding": total_outstanding,
        },
    )


@user_passes_test(lambda u: u.is_superuser)
def superuser_dashboard(request):
    total_users = User.objects.count()
    recent_users = User.objects.order_by("-date_joined")[:5]
    all_invoices = Invoice.objects.all()
    total_revenue = all_invoices.aggregate(total=Sum("total_amount"))["total"] or 0
    total_outstanding = sum(invoice.balance_due for invoice in all_invoices)

    context = {
        "total_users": total_users,
        "recent_users": recent_users,
        "total_revenue": total_revenue,
        "total_outstanding": total_outstanding,
    }
    return render(request, "admin/index.html", context)


@login_required
@user_passes_test(is_staff_or_admin)
def portfolio_summary(request):
    if not request.user.is_staff:
        return redirect("invoices:dashboard")

    manager = OpsManager.objects.get(pk=request.user.pk)
    tenants = manager.get_portfolio().select_related("user")
    currency_groups = {}

    for t in tenants:
        tenant_invoices = t.user.invoice_related.all()
        rev = sum(inv.total_amount for inv in tenant_invoices)
        out = sum(inv.balance_due for inv in tenant_invoices)
        t.total_revenue = rev
        t.total_outstanding = out

        curr = t.currency
        if curr not in currency_groups:
            currency_groups[curr] = {"revenue": 0, "outstanding": 0}
        currency_groups[curr]["revenue"] += rev
        currency_groups[curr]["outstanding"] += out

    return render(
        request,
        "core/portfolio_summary.html",
        {
            "tenants": tenants,
            "stats": currency_groups.items(),
        },
    )


@login_required
@user_passes_test(is_staff_or_admin)
def view_tenant_readonly(request, tenant_id):
    tenant_user = get_object_or_404(User, id=tenant_id, added_by=request.user)
    return render(
        request,
        "invoices/dashboard.html",
        {"target_tenant": tenant_user.profile, "read_only": True, "is_manager_view": True},
    )


# --- Public & Onboarding Views ---


@login_required
@require_POST
def dismiss_onboarding(request):
    is_permanent = request.POST.get("permanent") == "true"
    if is_permanent:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.show_onboarding_tips = False
        profile.save()
    return HttpResponse("")


@login_required
def initial_setup(request):
    user_profile = request.user.profile
    if request.method == "POST":
        dropdown_val = request.POST.get("currency_dropdown")
        custom_val = request.POST.get("currency_custom")
        is_vat = request.POST.get("is_vat") == "on"
        if dropdown_val == "OTHER" and custom_val:
            user_profile.currency = custom_val[:3]
        else:
            user_profile.currency = dropdown_val
        user_profile.is_vat_registered = is_vat
        user_profile.initial_setup_complete = True
        user_profile.save()
        return redirect("invoices:dashboard")
    return render(request, "core/initial_setup.html", {"profile": user_profile})


def contact_signup(request):
    submitted = False
    if request.method == "POST":
        form = AppInterestForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"]
            email = form.cleaned_data["email"]
            understanding = form.cleaned_data["understanding"]
            email_body = (
                f"New interest in the Billing App:\n\n"
                f"Name: {name}\n"
                f"Email: {email}\n\n"
                f"Understanding of the App:\n{understanding}"
            )
            try:
                send_mail(
                    subject=f"App Access Request: {name}",
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=["peter@diode.co.za"],
                    fail_silently=False,
                )
                submitted = True
                messages.success(request, "Your request has been sent to Peter.")
            except Exception:
                messages.error(request, "Unable to send email at this time.")
    else:
        form = AppInterestForm()
    return render(request, "registration/signup_contact.html", {"form": form, "submitted": submitted})


def landing_page(request):
    if request.user.is_authenticated:
        return redirect("invoices:dashboard")
    submitted = request.GET.get("submitted") == "true"
    if request.method == "POST" and "signup_request" in request.POST:
        form = AppInterestForm(request.POST)
        if form.is_valid():
            email_body = f"New Access Request\nName: {form.cleaned_data['name']}\nEmail: {form.cleaned_data['email']}"
            try:
                send_mail(
                    subject="App Access Request",
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=["peter@diode.co.za"],
                )
                return redirect("/?submitted=true")
            except Exception:
                messages.error(request, "Mail server error.")
    else:
        form = AppInterestForm()
    return render(request, "landing_page.html", {"form": form, "submitted": submitted})


# --- Admin & User Management ---


@user_passes_test(lambda u: u.is_superuser)
def admin_create_user(request):
    form = AdminUserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        username = form.cleaned_data["username"]
        if User.objects.filter(email=email).exists():
            messages.error(request, "A user with this email already exists.")
        else:
            User.objects.create_user(username=username, email=email, password=secrets.token_urlsafe(32))
            reset_form = PasswordResetForm(data={"email": email})
            if reset_form.is_valid():
                reset_form.save(request=request, from_email=settings.DEFAULT_FROM_EMAIL)
            messages.success(request, f"User {username} created and invite sent.")
            return redirect("invoices:dashboard")
    return render(request, "core/admin_create_user.html", {"form": form})


@login_required
def edit_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    form = UserProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Business profile updated.")
        response = redirect("invoices:dashboard")
        response["HX-Trigger"] = "profileUpdated"
        return response
    return render(request, "core/profile_form.html", {"form": form, "profile": profile})


@login_required
def update_profile(request):
    return edit_profile(request)


@login_required
@user_passes_test(is_staff_or_admin)
def manager_create_tenant(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Permission denied.")
    form = AdminUserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        username = email  # Use email as username for uniqueness
        if User.objects.filter(email=email).exists():
            messages.error(request, "A user with this email already exists.")
        else:
            try:
                user = User.objects.create_user(
                    username=username, email=email, password=secrets.token_urlsafe(32), added_by=request.user
                )
                reset_form = PasswordResetForm(data={"email": email})
                if reset_form.is_valid():
                    reset_form.save(request=request, from_email=settings.DEFAULT_FROM_EMAIL)
                messages.success(request, f"Tenant {email} created.")
                return redirect("core:portfolio_summary")
            except Exception as e:
                messages.error(request, f"Could not create user: {str(e)}")
    return render(request, "core/manager_create_tenant.html", {"form": form})


# --- Group Management (Staff) ---


@user_passes_test(lambda u: u.is_staff)
def staff_groups_list(request):
    groups = UserGroup.objects.filter(manager=request.user)
    return render(request, "core/staff_groups_list.html", {"groups": groups})


@user_passes_test(lambda u: u.is_staff)
def staff_group_create(request):
    form = UserGroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        group, created = UserGroup.objects.get_or_create(
            manager=request.user, defaults={"name": f"{request.user.username}'s Group"}
        )
        email = form.cleaned_data["add_user_email"]
        username = form.cleaned_data["add_user_username"]
        new_user = User.objects.create_user(username=username, email=email, password=secrets.token_urlsafe(32))
        GroupMember.objects.create(group=group, user=new_user, role="TENANT", added_by=request.user)
        messages.success(request, f"User {username} added to group.")
        return redirect("core:staff_groups_list")
    return render(request, "core/staff_group_form.html", {"form": form, "page_title": "Add User"})


@user_passes_test(lambda u: u.is_staff)
def staff_group_detail(request, group_id):
    group = get_object_or_404(UserGroup, id=group_id, manager=request.user)
    members = group.members.all()
    return render(request, "core/staff_group_detail.html", {"group": group, "members": members})


@user_passes_test(lambda u: u.is_staff)
def staff_add_group_member(request, group_id):
    group = get_object_or_404(UserGroup, id=group_id, manager=request.user)
    form = StaffCreateAndAddUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        username = form.cleaned_data["username"]
        new_user = User.objects.create_user(username=username, email=email, password=secrets.token_urlsafe(32))
        GroupMember.objects.create(group=group, user=new_user, role="TENANT", added_by=request.user)
        messages.success(request, f"User {username} added to {group.name}.")
        return redirect("core:staff_group_detail", group_id=group.id)
    return render(
        request,
        "core/staff_add_member_form.html",
        {"form": form, "group": group, "page_title": f"Add Member to {group.name}"},
    )


@user_passes_test(lambda u: u.is_staff)
@require_POST
def staff_remove_group_member(request, group_id, member_id):
    group = get_object_or_404(UserGroup, id=group_id, manager=request.user)
    member = get_object_or_404(GroupMember, id=member_id, group=group)
    username = member.user.username
    member.delete()
    messages.success(request, f"User {username} removed.")
    return redirect("core:staff_group_detail", group_id=group.id)

@login_required
def audit_settings(request):
    """View for users to configure invoice audit and anomaly detection."""
    profile = request.user.profile

    if request.method == "POST":
        form = AuditSettingsForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Audit settings updated successfully.")
            return redirect("core:audit_settings")
    else:
        form = AuditSettingsForm(instance=profile)

    # Pass trigger fields separately for the template
    trigger_fields = [
        form["detect_zero_total"],
        form["detect_no_items"],
        form["detect_statistical_outliers"],
        form["detect_missing_email"],
        form["detect_vat_mismatch"],
        form["detect_duplicate_items"],
    ]

    return render(
        request,
        "core/audit_settings.html",
        {"form": form, "trigger_fields": trigger_fields, "page_title": "Audit & Anomaly Detection Settings"},
    )


@login_required
def audit_history(request):
    """View for displaying audit history and comparison statistics."""
    from core.models import AuditHistory
    from decimal import Decimal
    from django.db import models

    # Get all audit decisions for this user
    all_audit_records = AuditHistory.objects.filter(user=request.user).select_related("invoice").order_by(
        "-created_at"
    )

    # Calculate statistics from ALL records
    total_audits = all_audit_records.count()
    flagged_count = all_audit_records.filter(is_flagged=True).count()
    approved_count = all_audit_records.filter(was_approved=True).count()

    # Average comparison stats
    avg_comparison_count = 0
    avg_cv = Decimal("0")

    if all_audit_records.exists():
        avg_comparison_count = int(
            all_audit_records.aggregate(models.Avg("comparison_invoices_count"))["comparison_invoices_count__avg"] or 0
        )
        avg_cv_val = all_audit_records.aggregate(models.Avg("comparison_cv"))["comparison_cv__avg"]
        if avg_cv_val:
            avg_cv = Decimal(str(avg_cv_val))

    # Get latest 50 records for display
    audit_records = all_audit_records[:50]

    # Format check names for display (remove 'detect_' prefix)
    for record in audit_records:
        if record.checks_run:
            record.formatted_checks = [check.replace("detect_", "") for check in record.checks_run]
        else:
            record.formatted_checks = []

    context = {
        "audit_records": audit_records,
        "total_audits": total_audits,
        "flagged_count": flagged_count,
        "flagged_percent": int((flagged_count / total_audits * 100)) if total_audits > 0 else 0,
        "approved_count": approved_count,
        "avg_comparison_count": avg_comparison_count,
        "avg_cv": avg_cv,
        "page_title": "Audit History & Statistics",
    }

    return render(request, "core/audit_history.html", context)