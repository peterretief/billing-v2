from django.contrib import admin

from .models import Event, GoogleCalendarCredential


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('get_category_name', 'client', 'status', 'priority', 'due_date', 'estimated_hours', 'created_at', 'user')
    list_filter = ('user', 'status', 'priority', 'client', 'created_at')
    search_fields = ('category__name', 'description', 'client__name')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    fieldsets = (
        ('Basic Info', {
            'fields': ('category', 'description', 'client')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority', 'due_date')
        }),
        ('Tracking', {
            'fields': ('estimated_hours', 'created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_category_name(self, obj):
        return obj.category.name if obj.category else 'Uncategorized'
    get_category_name.short_description = 'Category'


@admin.register(GoogleCalendarCredential)
class GoogleCalendarCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'sync_enabled', 'calendar_id', 'updated_at')
    list_filter = ('sync_enabled', 'user', 'updated_at')
    readonly_fields = ('access_token', 'refresh_token', 'token_expiry', 'created_at', 'updated_at')
    fieldsets = (
        ('User Info', {
            'fields': ('user',)
        }),
        ('Calendar', {
            'fields': ('calendar_id', 'sync_enabled')
        }),
        ('Token Info', {
            'fields': ('access_token', 'refresh_token', 'token_expiry'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
