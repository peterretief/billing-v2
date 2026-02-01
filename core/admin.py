from django.contrib import admin

from .models import User, UserProfile

admin.site.register(User)
#admin.site.register(UserProfile)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'show_onboarding_tips')