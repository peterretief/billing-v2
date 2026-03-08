from django.contrib import admin
from django.urls import include, path

from core import views as core_views
from core.views import brevo_webhook  # Import the view from your core app

urlpatterns = [
    path("webhooks/brevo/", brevo_webhook, name="brevo_webhook"),
    path("", include("core.urls")),  # Set landing page as the entry point
    path("admin/dashboard/", core_views.superuser_dashboard, name="admin_dashboard"),
    path("admin/", admin.site.urls),
    # This includes all built-in login/logout views
    path("accounts/", include("django.contrib.auth.urls")),
    # Our feature apps
    path("invoices/", include("invoices.urls")),
    path("clients/", include("clients.urls")),
    # path('core/', include('core.urls')), # This is now the root
    path("timesheets/", include("timesheets.urls")),
    path("calendar/", include("events.urls")),
    path("items/", include("items.urls")),
    path("notifications/", include("notifications.urls")),
    path("__debug__/", include("debug_toolbar.urls")),
    path("scheduler/", include("billing_schedule.urls")),
    # path("ops/", include("ops.urls")),  # Disabled for now, can be re-enabled later if needed
]
