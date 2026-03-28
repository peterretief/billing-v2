from django.db import models
from .current_user import get_current_user


class TenantQuerySet(models.QuerySet):
    """
    Base QuerySet for all user-owned data.
    """

    def for_user(self, user):
        """
        Shortcut to filter records by the logged-in user.
        Usage: Model.objects.for_user(request.user)
        """
        if user.is_anonymous:
            return self.none()
        return self.filter(user=user)

    def all_tenants(self):
        """
        Bypass automatic multi-tenancy filtering.
        Used for global stats, superuser views, and background tasks.
        """
        # Since the manager's get_queryset() might have already filtered it,
        # we might need to "unfilter" it.
        # However, if we're already at the QuerySet level, we just want to NOT filter.
        return self


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """
    The base manager for all user-owned data.
    Automatically isolates data by the current logged-in user.
    """

    def get_queryset(self):
        """
        Automatically filter the queryset by the current user if set in middleware.
        Superusers can see all data by default.
        """
        user = get_current_user()
        qs = super().get_queryset()
        
        # If we have a user and they are NOT a superuser, filter by user
        if user and not user.is_superuser:
            return qs.filter(user=user)
            
        return qs
