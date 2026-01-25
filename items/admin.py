# items/admin.py
from django.contrib import admin
from .models import Item

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('date', 'client', 'description', 'quantity', 'unit_price', 'total', 'is_billed', 'user')
    list_filter = ('is_billed', 'user', 'client')
    search_fields = ('description', 'client__name')
    date_hierarchy = 'date'
    ordering = ('-date',)