# /opt/billing_v2/invoices/admin.py
from django.contrib import admin

from core.models import BillingAuditLog

from .models import Coupon, CreditNote, Invoice, InvoiceEmailStatusLog, Payment


@admin.register(InvoiceEmailStatusLog)
class InvoiceEmailStatusLogAdmin(admin.ModelAdmin):
    list_display = ("invoice", "status", "created_at")  # Ensure this is created_at


@admin.register(BillingAuditLog)
class BillingAuditLogAdmin(admin.ModelAdmin):
    list_display = ("invoice", "is_anomaly", "ai_comment", "created_at")
    list_filter = ("is_anomaly", "created_at")
    search_fields = ("invoice__number", "ai_comment")
    readonly_fields = ("created_at", "details")


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ("reference", "client", "amount", "balance", "note_type", "issued_date")
    list_filter = ("note_type", "issued_date", "client")
    search_fields = ("reference", "client__name", "description")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Client & Invoice", {"fields": ("client", "invoice")}),
        ("Credit Details", {"fields": ("note_type", "amount", "balance", "issued_date")}),
        ("Documentation", {"fields": ("reference", "description")}),
        ("Audit Trail", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "discount_value", "current_uses", "max_uses", "valid_until", "is_active")
    list_filter = ("is_active", "discount_type", "valid_from", "valid_until")
    search_fields = ("code", "description")
    readonly_fields = ("current_uses", "created_at", "updated_at")

    fieldsets = (
        ("Coupon Code & Discount", {"fields": ("code", "discount_type", "discount_value", "description")}),
        ("Usage Limits", {"fields": ("max_uses", "current_uses")}),
        ("Validity", {"fields": ("is_active", "valid_from", "valid_until")}),
        ("Audit Trail", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


# Register your models here.
# invoices/admin.py
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    # Add 'is_template' to the list view
    list_display = ("number", "client", "date_issued", "total_amount", "status", "is_template")

    # This makes it a clickable checkbox right in the table!
    list_editable = ("is_template",)

    # Optional: Add a filter on the right sidebar
    list_filter = ("status", "is_template", "date_issued")
    
    def has_delete_permission(self, request):
        """Prevent deletion of invoices to maintain data integrity."""
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "credit_applied", "date_paid", "reference")
    list_filter = ("date_paid", "invoice__client")
    search_fields = ("invoice__number", "reference")
    readonly_fields = ("invoice",)
    
    def has_delete_permission(self, request):
        """Prevent deletion of payments to maintain invoice balance_due calculations."""
        return False
