# items/urls.py
from django.urls import path

from .views import (
    ItemCreateView,
    ItemDeleteView,
    ItemListView,
    ItemUpdateView,
    generate_invoice_from_items,
    trigger_billing,
)

app_name = 'items'

urlpatterns = [
    path('', ItemListView.as_view(), name='item_list'),
    path('create/', ItemCreateView.as_view(), name='item_create'),
    path('<int:pk>/update/', ItemUpdateView.as_view(), name='item_update'),
    path('<int:pk>/delete/', ItemDeleteView.as_view(), name='item_delete'),
    path('generate-invoice/', generate_invoice_from_items, name='generate_invoice_from_items'),
    path('trigger-billing/', trigger_billing, name='trigger_billing'),
]