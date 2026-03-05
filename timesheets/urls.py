# timesheets/urls.py
from django.urls import path

from . import views

app_name = "timesheets"

urlpatterns = [
    # The list of all timesheets
    path("", views.TimesheetListView.as_view(), name="timesheet_list"),
    # The endpoint our Modal posts to
    path("log/", views.log_time, name="log_time"),
    # (Optional) Delete or Edit paths
    path("<int:pk>/delete/", views.delete_entry, name="delete_entry"),
    path("generate-invoice-bulk/", views.generate_invoice_bulk, name="generate_invoice_bulk"),
    path("<int:pk>/edit/", views.edit_entry, name="edit_entry"),
    path("ajax/get-category-fields/", views.get_category_fields, name="get_category_fields"),
    path("categories/manage/", views.manage_categories, name="manage_categories"),
    path("categories/<int:pk>/edit/", views.edit_category, name="edit_category"),
    path("categories/<int:pk>/delete/", views.delete_category, name="delete_category"),
    path("reports/invoice/<int:invoice_id>/", views.invoice_time_report, name="invoice_time_report"),
    path("invoice/<int:invoice_id>/metadata-pdf/", views.export_metadata_pdf, name="export_metadata_pdf"),
    path("get-client-rate/", views.get_client_rate, name="get_client_rate"),
]
