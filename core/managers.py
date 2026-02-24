from django.db import models


class TenantManager(models.Manager):
    """
    The base manager for all user-owned data.
    """

    def for_user(self, user):
        """
        Shortcut to filter records by the logged-in user.
        Usage: Invoice.objects.for_user(request.user)
        """
        return self.get_queryset().filter(user=user)

    def get_queryset(self):
        # You could also override this to always filter,
        # but for_user() is safer for debugging.
        return super().get_queryset()
