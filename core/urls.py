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
 
]