from django.contrib import admin
from .models import Todo


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'status', 'priority', 'due_date', 'estimated_hours', 'created_at')
    list_filter = ('status', 'priority', 'client', 'created_at')
    search_fields = ('title', 'description', 'client__name')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'description', 'client')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority', 'due_date')
        }),
        ('Tracking', {
            'fields': ('estimated_hours', 'created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
