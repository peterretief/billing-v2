from django.urls import path

from . import recon_views, views, api

app_name = "invoices"

urlpatterns = [
    path("audit/mark-sorted/<int:pk>/", views.mark_anomaly_sorted, name="mark_anomaly_sorted"),
    path("audit/cancel/<int:pk>/", views.cancel_invoice_from_audit, name="cancel_invoice_from_audit"),
    path("<int:pk>/toggle-attach-timesheet/", views.toggle_attach_timesheet, name="toggle_attach_timesheet"),
    path("<int:pk>/toggle-quote-status/", views.toggle_quote_status, name="toggle_quote_status"),
    path("<int:pk>/convert-quote-to-invoice/", views.convert_quote_to_invoice, name="convert_quote_to_invoice"),
    path("<int:pk>/reject-quote/", views.reject_quote, name="reject_quote"),
    path("<int:pk>/send/", views.send_invoice, name="send_invoice"),
    # Dashboard & Lists
    path("<int:pk>/pdf/", views.generate_invoice_pdf_view, name="generate_invoice_pdf_view"),
    path("<int:pk>/pay/", views.mark_invoice_paid, name="mark_as_paid"),
    path("", views.dashboard, name="dashboard"),
    path("reports/revenue/", views.revenue_report, name="revenue_report"),
    path("list/", views.invoice_list, name="invoice_list"),
    # Client Statements (Year-end or custom period)
    path("client/<int:client_id>/statement/", views.client_statement, name="client_statement"),
    # Detail & Edit (Manual creation removed, use Timesheets to generate)
    path("<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("<int:pk>/edit/", views.invoice_edit, name="invoice_edit"),
    path("<int:pk>/duplicate/", views.duplicate_invoice, name="duplicate_invoice"),
    path("<int:pk>/delete/", views.delete_invoice, name="delete_invoice"),
    # Payments (The new unified logic)
    path("<int:pk>/pay/", views.mark_invoice_paid, name="mark_as_paid"),
    path("<int:pk>/record-payment/", views.record_payment, name="record_payment"),
    # PDF & Email
    path("<int:pk>/pdf/", views.generate_invoice_pdf_view, name="invoice_pdf"),
    path("<int:pk>/resend/", views.resend_invoice, name="resend_invoice"),
    path("<int:pk>/resend-modal/", views.get_resend_modal, name="get_resend_modal"),
    path("<int:pk>/send-modal/", views.get_send_modal, name="get_send_modal"),
    # VAT Reporting
    path("vat/generate/", views.generate_vat_report, name="generate_vat_report"),
    path("vat/<int:pk>/download/", views.download_vat_latex, name="download_vat_latex"),
    path("create/", views.invoice_create, name="invoice_create"),  # Add this!
    path("bulk-post/", views.bulk_post, name="bulk_post"),
    path("financial-assessment/", views.financial_assessment, name="financial_assessment"),
    path("record-vat-payment/", views.record_vat_payment, name="record_vat_payment"),
    path("vat-payment-history/", views.vat_payment_history_modal, name="vat_payment_history"),
    path("vat-payments/export-csv/", views.export_vat_payments_csv, name="export_vat_payments_csv"),
    path("audit-report/", views.billing_audit_report, name="billing_audit_report"),
    path("invoice/<int:pk>/payment-modal/", views.get_payment_modal, name="get_payment_modal"),
    # Reconciliation Statements
    path("reconciliation/", recon_views.all_clients_reconciliation, name="all_clients_reconciliation"),
    path(
        "reconciliation/export-csv/", recon_views.all_clients_reconciliation_csv, name="all_clients_reconciliation_csv"
    ),
    path(
        "reconciliation/client/<int:client_id>/",
        recon_views.client_reconciliation_statement,
        name="client_reconciliation",
    ),
    path(
        "reconciliation/client/<int:client_id>/pdf/",
        recon_views.client_reconciliation_pdf,
        name="client_reconciliation_pdf",
    ),
    path(
        "reconciliation/client/<int:client_id>/csv/",
        recon_views.client_reconciliation_csv,
        name="client_reconciliation_csv",
    ),
    # Credit Notes
    path("credit-note/create/", recon_views.create_credit_note, name="create_credit_note"),
    path("credit-note/create/<int:client_id>/", recon_views.create_credit_note, name="create_credit_note_for_client"),
    path("credit-notes/", recon_views.list_credit_notes, name="list_credit_notes"),
    
    # REST API Endpoints (External integrations)
    path("api/create/", api.create_invoice_from_external, name="api_create_invoice"),
    path("api/pdf/", api.get_invoice_pdf, name="api_get_pdf"),
]
