# items/urls.py
from django.urls import path


from .views import (
    ItemCreateView,
    ItemDeleteView,
    ItemListView,
    ItemUpdateView,
    generate_invoice_from_items,
    trigger_billing,
    create_item_from_inventory,
)
from .views_item_invoice_log import item_invoice_email_log

app_name = "items"

urlpatterns = [
    path("", ItemListView.as_view(), name="item_list"),
    path("create/", ItemCreateView.as_view(), name="item_create"),
    path("<int:pk>/update/", ItemUpdateView.as_view(), name="item_update"),
    path("<int:pk>/delete/", ItemDeleteView.as_view(), name="item_delete"),
    path("generate-invoice/", generate_invoice_from_items, name="generate_invoice_from_items"),
    path("trigger-billing/", trigger_billing, name="trigger_billing"),
    path("<int:item_id>/recurring-invoice-log/", item_invoice_email_log, name="item_invoice_email_log"),
    path("create-from-inventory/", create_item_from_inventory, name="create_from_inventory"),
]
