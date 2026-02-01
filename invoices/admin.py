from django.contrib import admin

from invoices.models import Invoice


# Register your models here.
# invoices/admin.py
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    # Add 'is_template' to the list view
    list_display = ('number', 'client', 'date_issued', 'total_amount', 'status', 'is_template')
    
    # This makes it a clickable checkbox right in the table!
    list_editable = ('is_template',)
    
    # Optional: Add a filter on the right sidebar
    list_filter = ('status', 'is_template', 'date_issued')