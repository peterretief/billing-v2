from django.contrib import admin
from django.urls import path, include
from invoices import views

urlpatterns = [
    path('', include('core.urls')), # Set landing page as the entry point

    path('admin/', admin.site.urls),
    # This includes all built-in login/logout views
    path('accounts/', include('django.contrib.auth.urls')), 
    # Our feature apps
    path('invoices/', include('invoices.urls')),
    path('clients/', include('clients.urls')),
    #path('core/', include('core.urls')), # This is now the root
    path('timesheets/', include('timesheets.urls')),
    path('notifications/', include('notifications.urls')),
    path('__debug__/', include('debug_toolbar.urls')),
    
]