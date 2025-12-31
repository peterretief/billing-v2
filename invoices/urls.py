from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    # Dashboard and Main Lists
    path('', views.invoice_list, name='list'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Invoice Management
    path('create/', views.invoice_create, name='create'),
    path('<int:pk>/', views.invoice_detail, name='detail'),
    path('<int:pk>/edit/', views.invoice_edit, name='edit'),
    path('<int:pk>/pdf/', views.generate_invoice_pdf_view, name='pdf'),
    
    # HTMX / Dynamic Row Helper
    path('add-item-row/', views.add_item_row, name='add_item_row'),

]