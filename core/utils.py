from django.db.models import Avg, StdDev
from statistics import stdev
from decimal import Decimal

from invoices.models import Invoice

from .models import UserGroup


def get_anomaly_status(user, invoice):
    """
    Detects anomalies relative to the user's own billing history.
    Uses mean and standard deviation to adapt to currency variance.
    
    For weaker currencies (ZAR, INR, etc), higher variance is expected.
    For stronger currencies (EUR, GBP, etc), lower variance is expected.
    
    Flags invoices that are statistical outliers (>2 std devs from mean).
    Adapts thresholds based on coefficient of variation.
    """
    comments = []
    is_anomaly = False
    
    # Get user's currency
    currency = user.profile.currency if hasattr(user, 'profile') else 'R'

    # 1. Zero or no items — always a problem regardless of currency
    has_no_items = not invoice.billed_items.exists()
    zero_total = float(invoice.total_amount) == 0

    if has_no_items:
        is_anomaly = True
        comments.append("No line items on invoice")

    if zero_total:
        is_anomaly = True
        comments.append("Invoice total is zero")

    # 2. Statistical anomaly using standard deviation (accounts for currency variance)
    recent_invoices = Invoice.objects.filter(
        user=user,
        status__in=['PENDING', 'PAID']
    ).values_list('total_amount', flat=True)[:50]  # Last 50 invoices
    
    if len(recent_invoices) >= 2:  # Need at least 2 data points for std dev
        amounts = [float(a) for a in recent_invoices]
        mean = sum(amounts) / len(amounts)
        
        if mean > 0:
            # Calculate standard deviation (adapts to currency)
            variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
            std_dev = variance ** 0.5
            
            # Coefficient of variation (CV) measures relative variance
            # CV > 0.8 means high variance (weaker currencies often have this)
            # CV < 0.2 means low variance (stable invoice patterns)
            cv = std_dev / mean if mean > 0 else 0
            
            current_amount = float(invoice.total_amount)
            
            # Minimum threshold to prevent false positives
            # Even with low variance, allow up to 15% variance as natural
            min_threshold = mean * 0.15
            adjusted_std_dev = max(std_dev, min_threshold)
            
            # Adaptive threshold: more lenient for high-variance currencies
            if cv > 0.8:
                # High variance: use 2.5 sigma (catches ~1.2% outliers)
                threshold_upper = mean + (2.5 * adjusted_std_dev)
                threshold_lower = mean - (2 * adjusted_std_dev)
            elif cv > 0.5:
                # Medium variance: use 2 sigma (catches ~2.3% outliers)
                threshold_upper = mean + (2 * adjusted_std_dev)
                threshold_lower = mean - (1.5 * adjusted_std_dev)
            else:
                # Low variance (stable): use 1.5 sigma (catches ~6.7% outliers)
                threshold_upper = mean + (1.5 * adjusted_std_dev)
                threshold_lower = mean - (1.5 * adjusted_std_dev)
            
            # Flag high outliers
            if current_amount > threshold_upper:
                ratio = current_amount / mean
                is_anomaly = True
                comments.append(f"Invoice is {ratio:.1f}x above your average (high outlier)")
            
            # Flag low outliers (but only if significantly low)
            if 0 < current_amount < threshold_lower and current_amount < mean * 0.1:
                ratio = current_amount / mean if mean > 0 else 0
                is_anomaly = True
                comments.append(f"Invoice is unusually low — {ratio*100:.1f}% of average")

    # 3. No client email — will fail to send
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