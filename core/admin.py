from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .models import GroupMember, User, UserGroup, UserProfile


# --- 1. User Profile Inline ---

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    verbose_name_plural = "Profile Settings"
    fk_name = "user"

    def has_delete_permission(self, request, obj=None):
        # Allow deletion only if it's a superuser 
        # or if we are deleting the whole User object
        return request.user.is_superuser


# --- 2. Custom User Admin ---
@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = (UserProfileInline,)

    list_display = ("email", "is_staff", "is_superuser", "is_active")
    list_filter = ("is_staff", "is_superuser", "is_active")

    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "added_by")}),
        (
            _("Permissions"),
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password"),
            },
        ),
    )
    search_fields = ("email",)


# --- 3. User Group Inlines ---
class UserGroupInline(admin.TabularInline):
    model = GroupMember
    extra = 1
    fields = ("user", "role", "added_by", "added_at")
    readonly_fields = ("added_by", "added_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            managed_group_ids = UserGroup.objects.filter(manager=request.user).values_list("id", flat=True)
            qs = qs.filter(group_id__in=managed_group_ids)
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            if not request.user.is_superuser:
                managed_groups = UserGroup.objects.filter(manager=request.user)
                existing_members = GroupMember.objects.filter(group__in=managed_groups).values_list(
                    "user_id", flat=True
                )
                kwargs["queryset"] = (
                    User.objects.exclude(id__in=existing_members).exclude(is_superuser=True).exclude(is_staff=True)
                )
            else:
                kwargs["queryset"] = User.objects.filter(is_superuser=False)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# --- 4. User Group Admin ---
@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "manager", "member_count", "created_at")
    list_filter = ("manager", "created_at")
    search_fields = ("name", "description", "manager__email")
    readonly_fields = ("created_at", "updated_at")
    inlines = [UserGroupInline]

    fieldsets = (
        ("Group Information", {"fields": ("name", "description")}),
        (
            "Manager & Ownership",
            {"fields": ("manager",), "description": "Assign a staff member (Ops) to manage this group."},
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def member_count(self, obj):
        return obj.members.count()

    member_count.short_description = "Members"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Allow superusers and staff to see all groups
        if not (request.user.is_superuser or request.user.is_staff):
            qs = qs.filter(manager=request.user)
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "manager":
            if not request.user.is_superuser:
                kwargs["queryset"] = User.objects.filter(id=request.user.id)
            else:
                # Can select anyone with staff status
                kwargs["queryset"] = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and not obj.manager:
            obj.manager = request.user
        super().save_model(request, obj, form, change)


# --- 5. Group Member Admin ---
@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "role", "added_by", "added_at")
    list_filter = ("role", "group__manager", "added_at")
    search_fields = ("user__email", "group__name", "added_by__email")
    readonly_fields = ("added_by", "added_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not (request.user.is_superuser or request.user.is_staff):
            managed_group_ids = UserGroup.objects.filter(manager=request.user).values_list("id", flat=True)
            qs = qs.filter(group_id__in=managed_group_ids)
        return qs

    def save_model(self, request, obj, form, change):
        if not obj.added_by_id:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)


# --- 6. User Profile Admin ---
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company_name", "currency", "is_vat_registered")
    list_filter = ("is_vat_registered", "currency")
    search_fields = ("user__email", "company_name")
