
# /opt/billing_v2/invoices/admin.py
from django.contrib import admin

from .models import Invoice, InvoiceEmailStatusLog  # Update this name


@admin.register(InvoiceEmailStatusLog)
class InvoiceEmailStatusLogAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'status', 'created_at') # Ensure this is created_at

    
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