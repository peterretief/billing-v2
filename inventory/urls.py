from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_item_list, name='item_list'),
    path('items/create/', views.inventory_item_create, name='item_create'),
    path('items/<int:pk>/', views.inventory_item_detail, name='item_detail'),
    path('items/<int:pk>/update/', views.inventory_item_update, name='item_update'),
    path('items/<int:pk>/print-barcode/', views.print_barcode, name='print_barcode'),
    path('items/barcode/', views.item_by_barcode, name='item_by_barcode'),
    path('warehouses/', views.warehouse_list, name='warehouse_list'),
    path('warehouses/create/', views.warehouse_create, name='warehouse_create'),
    path('transactions/create/', views.stock_transaction_create, name='transaction_create'),
]
