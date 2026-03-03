# Register your models here.
from django.contrib import admin
from .models import BillingPolicy


@admin.register(BillingPolicy)
class BillingPolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_schedule_type', 'is_active', 'user')
    list_filter = ('is_active', 'special_rule')
    search_fields = ('name', 'user__username')
    
    fieldsets = (
        ('Policy Details', {
            'fields': ('user', 'name', 'is_active'),
        }),
        ('Schedule Type', {
            'fields': ('special_rule', 'run_day'),
        }),
    )
    
    def get_schedule_type(self, obj):
        if obj.special_rule == "WORK":
            return "First Working Day of Month"
        return f"Exact Date: {obj.run_day}th of Month"
    get_schedule_type.short_description = "Schedule Type"
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['run_day'].help_text = "1-31: specific date (or leave blank for First Working Day)"
        form.base_fields['special_rule'].help_text = "NONE = exact date mode, WORK = first working day of month"
        return form

