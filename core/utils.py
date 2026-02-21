from django.db.models import Avg

from invoices.models import Invoice

from .models import UserGroup


def get_anomaly_status(user, invoice):
    """
    Detects anomalies relative to the user's own billing history
    rather than a fixed currency amount.
    """
    comments = []
    is_anomaly = False

    # 1. Zero or no items — always a problem regardless of currency
    has_no_items = not invoice.billed_items.exists()
    zero_total = float(invoice.total_amount) == 0

    if has_no_items:
        is_anomaly = True
        comments.append("No line items on invoice")

    if zero_total:
        is_anomaly = True
        comments.append("Invoice total is zero")

    # 2. Statistical anomaly — flag if > 3x the user's average invoice
    avg = Invoice.objects.filter(
        user=user,
        status__in=['PENDING', 'PAID']
    ).aggregate(avg=Avg('total_amount'))['avg']

    if avg and avg > 0:
        ratio = float(invoice.total_amount) / float(avg)
        if ratio > 3:
            is_anomaly = True
            comments.append(f"Invoice is {ratio:.1f}x above your average ({avg:.2f})")

    # 3. Unusually low — might indicate a data entry error
    if avg and avg > 0:
        ratio = float(invoice.total_amount) / float(avg)
        if 0 < ratio < 0.1:
            is_anomaly = True
            comments.append(f"Invoice is unusually low — only {ratio*100:.1f}% of your average")

    # 4. No client email — will fail to send
    if not invoice.client.email:
        is_anomaly = True
        comments.append("Client has no email address")

    comment = " | ".join(comments) if comments else "OK"
    return is_anomaly, comment

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