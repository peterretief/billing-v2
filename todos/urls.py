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
]
