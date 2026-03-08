from django.urls import path
from . import views

app_name = 'events'

urlpatterns = [
    # List and create
    path('', views.EventListView.as_view(), name='event_list'),
    path('create/', views.EventCreateView.as_view(), name='event_create'),
    
    # Detail, update, delete
    path('<int:pk>/', views.EventDetailView.as_view(), name='event_detail'),
    path('<int:pk>/edit/', views.EventUpdateView.as_view(), name='event_edit'),
    path('<int:pk>/delete/', views.EventDeleteView.as_view(), name='event_delete'),
    
    # Actions
    path('<int:pk>/complete/', views.mark_event_completed, name='event_complete'),
    path('<int:pk>/cancel/', views.mark_event_cancelled, name='event_cancel'),
    
    # Google Calendar integration
    path('calendar/auth/start/', views.calendar_auth_start, name='calendar_auth_start'),
    path('calendar/auth/callback/', views.calendar_auth_callback, name='calendar_auth_callback'),
    path('calendar/sync/', views.sync_events_to_calendar, name='calendar_sync'),
    path('calendar/import/', views.import_calendar_events, name='import_calendar_events'),
    path('calendar/import-create-timesheets/', views.create_timesheets_from_events, name='create_timesheets_from_events'),
    
    
    # Scheduling API
    path('api/find-slots/', views.find_available_slots_api, name='find_available_slots_api'),
]
