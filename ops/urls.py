from django.urls import path

from . import views

app_name = 'ops'

urlpatterns = [
    path('dashboard/', views.OpsDashboardView.as_view(), name='dashboard'),
    path('invite-tenant/', views.invite_tenant_view, name='invite_tenant'),
]