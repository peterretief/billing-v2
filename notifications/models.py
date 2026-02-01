from django.db import models

from core.models import TenantModel


class Notification(TenantModel):
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    priority = models.IntegerField(default=0)

    def __str__(self):
        return self.message
