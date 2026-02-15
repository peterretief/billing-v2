    # Profile Management
from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('admin/create_user/', views.admin_create_user, name='admin_create_user'),
    # Dashboard and Main Lists
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    path('signup/', views.contact_signup, name='signup'),
    path('hide-onboarding/', views.dismiss_onboarding, name='hide_onboarding'),
    path('setup/', views.initial_setup, name='initial_setup'),
   
    path('portfolio/', views.portfolio_summary, name='portfolio_summary'),
    path('portfolio/add/', views.manager_create_tenant, name='manager_create_tenant'),
    path('portfolio/inspect/<int:tenant_id>/', views.view_tenant_readonly, name='view_tenant_readonly'),
    path('portfolio/report/<int:tenant_id>/', views.tenant_report_detail, name='tenant_report_detail'),
      ]