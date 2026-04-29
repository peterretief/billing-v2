from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core import views as core_views
from core.views import brevo_webhook, custom_logout  # Import the view from your core app
from larder.views import ProductMasterViewSet, GroceryStoreViewSet, TokenVerifyView

# API Router for larder microservice integration
api_router = DefaultRouter()
api_router.register(r'products', ProductMasterViewSet, basename='api-product')
api_router.register(r'stores', GroceryStoreViewSet, basename='api-store')

urlpatterns = [
    path("webhooks/brevo/", brevo_webhook, name="brevo_webhook"),
    path("", include("core.urls")),  # Set landing page as the entry point
    path("admin/dashboard/", core_views.superuser_dashboard, name="admin_dashboard"),
    path("admin/", admin.site.urls),
    # Custom logout that bypasses CSRF (since middleware is disabled)
    path("accounts/logout/", custom_logout, name="logout"),
    # This includes all built-in login/logout views (logout will use our custom one above)
    path("accounts/", include("django.contrib.auth.urls")),
    # django-select2 URLs
    path("select2/", include("django_select2.urls")),
    # Our feature apps
    path("invoices/", include("invoices.urls")),
    path("clients/", include("clients.urls")),
    # path('core/', include('core.urls')), # This is now the root
    path("timesheets/", include("timesheets.urls")),
#    path("calendar/", include("events.urls")),
    path("items/", include("items.urls")),
    path("notifications/", include("notifications.urls")),
    path("__debug__/", include("debug_toolbar.urls")),
    path("scheduler/", include("billing_schedule.urls")),
    path("inventory/", include("inventory.urls")),
    path("integrations/", include("integrations.urls")),
    path('larder/', include('larder.urls')),
    # API endpoints for larder microservice
    path('api/', include(api_router.urls)),
    path('api/auth/verify/', TokenVerifyView.as_view(), name='api-token-verify'),
    # path("recipes/", include("recipes.urls")),
    # path("ops/", include("ops.urls")),  # Disabled for now, can be re-enabled later if needed
]
