# items/managers.py
from django.db import models
from django.db.models import F, Sum


class ItemManager(models.Manager):
    def unbilled(self, user):
        return self.filter(user=user, is_billed=False)

    def total_unbilled_value(self, user, client=None):
        queryset = self.unbilled(user)
        if client:
            queryset = queryset.filter(client=client)

        result = queryset.aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )
        return result['total'] or 0
