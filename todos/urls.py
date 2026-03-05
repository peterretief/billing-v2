from django.urls import path
from . import views

app_name = 'todos'

urlpatterns = [
    # List and create
    path('', views.TodoListView.as_view(), name='todo_list'),
    path('create/', views.TodoCreateView.as_view(), name='todo_create'),
    
    # Detail, update, delete
    path('<int:pk>/', views.TodoDetailView.as_view(), name='todo_detail'),
    path('<int:pk>/edit/', views.TodoUpdateView.as_view(), name='todo_edit'),
    path('<int:pk>/delete/', views.TodoDeleteView.as_view(), name='todo_delete'),
    
    # Actions
    path('<int:pk>/complete/', views.mark_todo_completed, name='todo_complete'),
    path('<int:pk>/cancel/', views.mark_todo_cancelled, name='todo_cancel'),
    
    # Google Calendar integration
    path('calendar/auth/start/', views.calendar_auth_start, name='calendar_auth_start'),
    path('calendar/auth/callback/', views.calendar_auth_callback, name='calendar_auth_callback'),
    path('calendar/sync/', views.sync_todos_to_calendar, name='calendar_sync'),
    path('calendar/import/', views.import_calendar_events, name='import_calendar_events'),
    path('calendar/import-create-timesheets/', views.create_timesheets_from_events, name='create_timesheets_from_events'),
    
    # Google Contacts integration
    path('contacts/sync/', views.sync_contacts_page, name='sync_contacts_page'),
    path('contacts/sync-now/', views.sync_clients_to_contacts, name='sync_clients_to_contacts'),
]
