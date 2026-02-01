from core.models import BillingAuditLog

# Delete logs where the associated invoice has been deleted
BillingAuditLog.objects.filter(invoice__isnull=True).delete()