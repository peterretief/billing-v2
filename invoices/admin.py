
# /opt/billing_v2/invoices/admin.py
from django.contrib import admin

from .models import Invoice, InvoiceEmailStatusLog, CreditNote
from core.models import BillingAuditLog


@admin.register(InvoiceEmailStatusLog)
class InvoiceEmailStatusLogAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'status', 'created_at') # Ensure this is created_at


@admin.register(BillingAuditLog)
class BillingAuditLogAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'is_anomaly', 'ai_comment', 'created_at')
    list_filter = ('is_anomaly', 'created_at')
    search_fields = ('invoice__number', 'ai_comment')
    readonly_fields = ('created_at', 'details')


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ('reference', 'client', 'amount', 'balance', 'note_type', 'issued_date')
    list_filter = ('note_type', 'issued_date', 'client')
    search_fields = ('reference', 'client__name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Client & Invoice', {
            'fields': ('client', 'invoice')
        }),
        ('Credit Details', {
            'fields': ('note_type', 'amount', 'balance', 'issued_date')
        }),
        ('Documentation', {
            'fields': ('reference', 'description')
        }),
        ('Audit Trail', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


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