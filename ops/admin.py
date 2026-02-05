
# Register your models here.
from django.contrib import admin

from .models import BillingBatch


@admin.register(BillingBatch)
class BillingBatchAdmin(admin.ModelAdmin):
    list_display = ('user', 'scheduled_date', 'is_processed', 'processed_at', 'invoice_count')
    list_filter = ('is_processed', 'scheduled_date')
    search_fields = ('user__username', 'user__email')