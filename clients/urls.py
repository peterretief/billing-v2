from django.urls import path

from . import views

app_name = "clients"

urlpatterns = [
    # 1. List & Detail
    path("", views.ClientListView.as_view(), name="client_list"),
    path("<int:pk>/", views.ClientDetailView.as_view(), name="client_detail"),
    # 2. Add & Edit (Both use the same 'client_edit' view function)
    path("add/", views.client_edit, name="client_add"),
    path("edit/<int:pk>/", views.client_edit, name="client_edit"),
    # 3. Financial Statement
    path("statement/<int:pk>/", views.client_statement, name="client_statement"),
    path("statement/<int:pk>/csv/", views.client_statement_csv, name="client_statement_csv"),
    # 4. Summary Dashboard
    path("summary/", views.clients_summary_dashboard, name="clients_summary_dashboard"),
    path("summary/<int:pk>/", views.client_summary_detail, name="client_summary_detail"),
]
