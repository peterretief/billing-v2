from .models import UserGroup


def get_isolated_queryset(user, model_class):
    """
    The 'Unix Filter' for your data. 
    Pass in a user and a model (like Invoice), 
    and it returns only the records they are allowed to see.
    """
    qs = model_class.objects.all()

    # 1. Superusers: The 'root' users of your app
    if user.is_superuser:
        return qs

    # 2. Staff/Managers: See data for groups they manage
    if user.is_staff or getattr(user, 'is_ops', False):
        managed_groups = UserGroup.objects.filter(manager=user)
        return qs.filter(group__in=managed_groups)

    # 3. Tenants: See only data for groups they are members of
    tenant_groups = UserGroup.objects.filter(members__user=user)
    return qs.filter(group__in=tenant_groups)