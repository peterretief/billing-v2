from django.urls import path

from . import views

app_name = 'clients'

urlpatterns = [
    # 1. List & Detail
    path('', views.ClientListView.as_view(), name='client_list'),
    path('<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),

    # 2. Add & Edit (Both use the same 'client_edit' view function)
    path('add/', views.client_edit, name='client_add'), 
    path('edit/<int:pk>/', views.client_edit, name='client_edit'),

    # 3. Financial Statement
    path('statement/<int:pk>/', views.client_statement, name='client_statement'),

]