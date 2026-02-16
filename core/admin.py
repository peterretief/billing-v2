from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Q

from .models import GroupMember, User, UserGroup, UserProfile

# Register User with default Django admin (superusers only)
admin.site.register(User, DjangoUserAdmin)


class UserGroupInline(admin.TabularInline):
    """Inline admin for group members."""
    model = GroupMember
    extra = 1
    fields = ('user', 'role', 'added_by', 'added_at')
    readonly_fields = ('added_by', 'added_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Non-superusers can only see members in their own groups
        if not request.user.is_superuser:
            managed_group_ids = UserGroup.objects.filter(
                manager=request.user
            ).values_list('id', flat=True)
            qs = qs.filter(group_id__in=managed_group_ids)
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Restrict user choices based on permissions."""
        if db_field.name == 'user':
            if not request.user.is_superuser:
                # Managers can only add bound tenants to their own group
                managed_groups = UserGroup.objects.filter(
                    manager=request.user
                )
                existing_members = GroupMember.objects.filter(
                    group__in=managed_groups
                ).values_list('user_id', flat=True)
                # Show only users not already in manager's groups and not staff/superuser
                kwargs['queryset'] = User.objects.exclude(
                    id__in=existing_members
                ).exclude(is_superuser=True).exclude(is_staff=True)
            else:
                # Superuser can add any user that's not already a superuser
                kwargs['queryset'] = User.objects.filter(is_superuser=False)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'manager', 'member_count', 'created_at')
    list_filter = ('manager', 'created_at')
    search_fields = ('name', 'description', 'manager__username')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [UserGroupInline]
    
    fieldsets = (
        ('Group Information', {
            'fields': ('name', 'description')
        }),
        ('Manager & Ownership', {
            'fields': ('manager',),
            'description': 'Leave empty for superuser-only groups. Select a manager to allow them to manage this group.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def member_count(self, obj):
        """Display count of members in the group."""
        return obj.members.count()
    member_count.short_description = "Members"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Superusers see all groups
        if not request.user.is_superuser:
            # Managers see only their own groups
            qs = qs.filter(manager=request.user)
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Restrict manager choices - only admins can assign groups."""
        if db_field.name == 'manager':
            if not request.user.is_superuser:
                # Managers can only see themselves
                kwargs['queryset'] = User.objects.filter(id=request.user.id)
            else:
                # Superuser can select any staff user as manager
                kwargs['queryset'] = User.objects.filter(
                    Q(is_staff=True) & Q(is_superuser=False)
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Ensure non-superusers can only manage their own groups."""
        if not request.user.is_superuser and obj.manager_id != request.user.id:
            obj.manager = request.user
        super().save_model(request, obj, form, change)


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'role', 'added_by', 'added_at')
    list_filter = ('role', 'group__manager', 'added_at')
    search_fields = ('user__username', 'group__name', 'added_by__username')
    readonly_fields = ('added_by', 'added_at')
    
    fieldsets = (
        ('Membership Details', {
            'fields': ('group', 'user', 'role')
        }),
        ('Audit Trail', {
            'fields': ('added_by', 'added_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Superusers see all memberships
        if not request.user.is_superuser:
            # Managers see only memberships in their groups
            managed_group_ids = UserGroup.objects.filter(
                manager=request.user
            ).values_list('id', flat=True)
            qs = qs.filter(group_id__in=managed_group_ids)
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Restrict choices based on permissions."""
        if db_field.name == 'group':
            if not request.user.is_superuser:
                # Managers can only add to their own groups
                kwargs['queryset'] = UserGroup.objects.filter(
                    manager=request.user
                )
            # Superuser sees all groups
        elif db_field.name == 'user':
            if not request.user.is_superuser:
                # Managers can only add bound tenants (non-staff users)
                managed_groups = UserGroup.objects.filter(
                    manager=request.user
                )
                existing_members = GroupMember.objects.filter(
                    group__in=managed_groups
                ).values_list('user_id', flat=True)
                kwargs['queryset'] = User.objects.filter(
                    is_staff=False,
                    is_superuser=False
                ).exclude(id__in=existing_members)
            else:
                # Superuser can add any non-superuser
                kwargs['queryset'] = User.objects.filter(is_superuser=False)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Set added_by to current user."""
        if not obj.added_by_id:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'company_name', 'currency', 'is_vat_registered')
    list_filter = ('is_vat_registered', 'currency')
    search_fields = ('user__username', 'company_name')