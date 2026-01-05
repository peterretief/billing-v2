# timesheets/urls.py
from django.urls import path
from . import views

app_name = 'timesheets'

urlpatterns = [
    # The list of all timesheets
    path('', views.TimesheetListView.as_view(), name='timesheet_list'),
    
    # The endpoint our Modal posts to
    path('log/', views.log_time, name='log_time'),
    
    # (Optional) Delete or Edit paths
    path('<int:pk>/delete/', views.delete_entry, name='delete_entry'),

    path('generate-invoice-bulk/', views.generate_invoice_bulk, name='generate_invoice_bulk'),

    path('<int:pk>/edit/', views.edit_entry, name='edit_entry'),
    path('ajax/get-category-fields/', views.get_category_fields, name='get_category_fields'),
]