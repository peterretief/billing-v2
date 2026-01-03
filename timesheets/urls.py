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
    path('<int:pk>/delete/', views.delete_entry, name='timesheet_delete'),
]