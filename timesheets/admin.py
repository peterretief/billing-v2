from django.contrib import admin

from .models import DefaultWorkCategory, TimesheetEntry, WorkCategory

admin.site.register(WorkCategory)
admin.site.register(TimesheetEntry)
admin.site.register(DefaultWorkCategory)
