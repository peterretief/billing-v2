from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'email', 'created_at')
    list_filter = ('user',)
    search_fields = ('name', 'email')