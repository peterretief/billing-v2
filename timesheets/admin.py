
# Register your models here.
from django.contrib import admin
from .models import TimesheetEntry, WorkCategory


admin.site.register(WorkCategory)
admin.site.register(TimesheetEntry)