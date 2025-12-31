    # Profile Management

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Dashboard and Main Lists
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    path('profile/success/', views.profile_success, name='profile_success'),

]