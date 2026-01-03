from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    path('', views.invoice_list, name='invoice_list'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('create/', views.invoice_create, name='invoice_create'),
    path('<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('<int:pk>/pdf/', views.generate_invoice_pdf_view, name='invoice_pdf'),
    path('<int:pk>/mark-paid/', views.mark_invoice_paid, name='mark_paid'),
    path('<int:pk>/status/<str:new_status>/', views.mark_status, name='mark_status'),
    path('<int:pk>/resend/', views.resend_invoice, name='resend_invoice'),
    path('bulk-post/', views.bulk_post_invoices, name='bulk_post'),
]