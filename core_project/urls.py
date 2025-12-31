from django.contrib import admin
from django.urls import path, include
from invoices import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'), # Base invoices/ URL

    path('admin/', admin.site.urls),
    # This includes all built-in login/logout views
    path('accounts/', include('django.contrib.auth.urls')), 
    # Our feature apps
    path('invoices/', include('invoices.urls')),
    path('clients/', include('clients.urls')),
    path('core/', include('core.urls')),
]