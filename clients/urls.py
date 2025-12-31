
from django.urls import path
from . import views

app_name = 'clients'

urlpatterns = [
    path('', views.ClientListView.as_view(), name='list'),
    # Ensure this line exists and the name is exactly 'create'
    path('add/', views.ClientCreateView.as_view(), name='create'), 
    path('<int:pk>/', views.ClientDetailView.as_view(), name='detail'),
]