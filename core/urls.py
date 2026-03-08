# Profile Management
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing_page, name="landing_page"),
    path("admin/create_user/", views.admin_create_user, name="admin_create_user"),
    # Dashboard and Main Lists
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("profile/update/", views.update_profile, name="update_profile"),
    path("signup/", views.contact_signup, name="signup"),
    path("hide-onboarding/", views.dismiss_onboarding, name="hide_onboarding"),
    path("setup/", views.initial_setup, name="initial_setup"),
    path("portfolio/", views.portfolio_summary, name="portfolio_summary"),
    path("portfolio/add/", views.manager_create_tenant, name="manager_create_tenant"),
    path("portfolio/inspect/<int:tenant_id>/", views.view_tenant_readonly, name="view_tenant_readonly"),
    path("portfolio/report/<int:tenant_id>/", views.tenant_report_detail, name="tenant_report_detail"),
    # Staff Group Management
    path("staff/groups/", views.staff_groups_list, name="staff_groups_list"),
    path("staff/groups/create/", views.staff_group_create, name="staff_group_create"),
    path("staff/groups/<int:group_id>/", views.staff_group_detail, name="staff_group_detail"),
    path("staff/groups/<int:group_id>/add-member/", views.staff_add_group_member, name="staff_add_group_member"),
    path(
        "staff/groups/<int:group_id>/member/<int:member_id>/remove/",
        views.staff_remove_group_member,
        name="staff_remove_group_member",
    ),
    # core/urls.py
    path("email-status/", views.email_status_view, name="email_status"),  # MAIN PAGE
    path("email-status/rows/", views.email_status_rows, name="email_status_rows"),  # PARTIAL
    path("email-status/sync/<int:invoice_id>/", views.sync_invoice_status, name="sync_invoice_status"),
    path("api/invoice-delivery-statuses/", views.api_invoice_delivery_statuses, name="api_invoice_delivery_statuses"),
    path("recurring-invoices-report/", views.recurring_invoices_report, name="recurring_invoices_report"),
    # Audit Settings
    path("audit-settings/", views.audit_settings, name="audit_settings"),
    path("audit-history/", views.audit_history, name="audit_history"),
    # Working Hours Settings
    path("working-hours/", views.working_hours_settings, name="working_hours_settings"),
]
