from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('api/notifications/', views.get_notifications, name='get_notifications'),
]
