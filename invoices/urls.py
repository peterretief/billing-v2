from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    path('audit/mark-sorted/<int:pk>/', views.mark_anomaly_sorted, name='mark_anomaly_sorted'),
        path('<int:pk>/toggle-attach-timesheet/', views.toggle_attach_timesheet, name='toggle_attach_timesheet'),
    # Dashboard & Lists
    path('<int:pk>/pdf/', views.generate_invoice_pdf_view, name='generate_invoice_pdf_view'),
    path('<int:pk>/pay/', views.mark_invoice_paid, name='mark_as_paid'),
    path('', views.dashboard, name='dashboard'),
    path('list/', views.invoice_list, name='invoice_list'),
    
    # Detail & Edit (Manual creation removed, use Timesheets to generate)
    path('<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('<int:pk>/duplicate/', views.duplicate_invoice, name='duplicate_invoice'),
    path('<int:pk>/delete/', views.delete_invoice, name='delete_invoice'),

    # Payments (The new unified logic)
    path('<int:pk>/pay/', views.mark_invoice_paid, name='mark_as_paid'),
    path('<int:pk>/record-payment/', views.record_payment, name='record_payment'),

    # PDF & Email
    path('<int:pk>/pdf/', views.generate_invoice_pdf_view, name='invoice_pdf'),
    path('<int:pk>/resend/', views.resend_invoice, name='resend_invoice'),
    path('<int:pk>/resend-modal/', views.get_resend_modal, name='get_resend_modal'),

    # VAT Reporting
    path('vat/generate/', views.generate_vat_report, name='generate_vat_report'),
    path('vat/<int:pk>/download/', views.download_vat_latex, name='download_vat_latex'),
    path('create/', views.invoice_create, name='invoice_create'), # Add this!
    path('bulk-post/', views.bulk_post, name='bulk_post'),
    path('financial-assessment/', views.financial_assessment, name='financial_assessment'),
    path('record-vat-payment/', views.record_vat_payment, name='record_vat_payment'),
    path('audit-report/', views.billing_audit_report, name='billing_audit_report'),
    path('invoice/<int:pk>/payment-modal/', views.get_payment_modal, name='get_payment_modal'),
]