from django.urls import path

from . import views

app_name = 'billing_schedule'

urlpatterns = [
    # The list of all policies
    path('policies/', views.policy_list, name='policy_list'),
    
    # The form to create a new one
    path('policies/create/', views.create_policy, name='create'),
    
    # Optional: Edit and Delete
    path('policies/<int:pk>/edit/', views.edit_policy, name='edit'),
    path('policies/<int:pk>/delete/', views.delete_policy, name='delete'),
]