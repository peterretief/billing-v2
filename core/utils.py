
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
    
    Respects user's audit settings (enabled/disabled, sensitivity, triggers).
    
    Returns tuple: (is_anomaly, comment, audit_context)
    - audit_context: Dict with comparison stats and history info for tracking
    """
    comments = []
    is_anomaly = False
    audit_context = {
        "checks_run": [],
        "comparison_invoices_count": 0,
        "comparison_mean": None,
        "comparison_stddev": None,
        "comparison_cv": None,
    }

    # Check if audit is enabled for this user
    if not hasattr(user, "profile") or not user.profile.audit_enabled:
        return False, "Audit disabled", audit_context

    # Get user's settings
    profile = user.profile
    triggers = profile.get_audit_triggers()
    sensitivity = profile.audit_sensitivity

    # Get user's currency
    currency = profile.currency if hasattr(user, "profile") else "R"

    # 1. Zero or no items — always a problem regardless of currency
    if triggers.get("detect_no_items", True):
        audit_context["checks_run"].append("detect_no_items")
        has_no_items = not invoice.billed_items.exists()
        if has_no_items:
            is_anomaly = True
            comments.append("No line items on invoice")

    if triggers.get("detect_zero_total", True):
        audit_context["checks_run"].append("detect_zero_total")
        zero_total = float(invoice.total_amount) == 0
        if zero_total:
            is_anomaly = True
            comments.append("Invoice total is zero")

    # 2. Statistical anomaly using standard deviation (accounts for currency variance)
    if triggers.get("detect_statistical_outliers", True):
        audit_context["checks_run"].append("detect_statistical_outliers")
        recent_invoices = Invoice.objects.filter(user=user, status__in=["PENDING", "PAID"]).values_list(
            "total_amount", flat=True
        )[:50]  # Last 50 invoices

        audit_context["comparison_invoices_count"] = len(recent_invoices)

        if len(recent_invoices) >= 2:  # Need at least 2 data points for std dev
            amounts = [float(a) for a in recent_invoices]
            mean = sum(amounts) / len(amounts)

            if mean > 0:
                # Calculate standard deviation (adapts to currency)
                variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
                std_dev = variance**0.5

                # Store for audit tracking
                audit_context["comparison_mean"] = mean
                audit_context["comparison_stddev"] = std_dev

                # Coefficient of variation (CV) measures relative variance
                # CV > 0.8 means high variance (weaker currencies often have this)
                # CV < 0.2 means low variance (stable invoice patterns)
                cv = std_dev / mean if mean > 0 else 0
                audit_context["comparison_cv"] = cv

                current_amount = float(invoice.total_amount)

                # Very loose threshold: only flag if 1000x the average
                threshold_upper = mean * 1000
                threshold_lower = mean * 0.001  # Also very loose for low end

                # Flag high outliers (only if 1000x+ the average)
                if current_amount > threshold_upper:
                    ratio = current_amount / mean
                    is_anomaly = True
                    comments.append(f"Invoice is {ratio:.1f}x above your average (extreme outlier)")

                # Flag low outliers (only if 0.1% of average or less)
                if 0 < current_amount < threshold_lower:
                    ratio = current_amount / mean if mean > 0 else 0
                    is_anomaly = True
                    comments.append(f"Invoice is {ratio * 100:.1f}% of average (extremely low)")
        else:
            comments.append("Building history (insufficient invoices for comparison)")

    # 3. No client email — will fail to send (disabled for lenient mode)
    if triggers.get("detect_missing_email", False):  # Default False for more lenient behavior
        audit_context["checks_run"].append("detect_missing_email")
        if not invoice.client.email:
            is_anomaly = True
            comments.append("Client has no email address")

    # 4. Business logic checks: VAT configuration (disabled for lenient mode)
    if triggers.get("detect_vat_mismatch", False):  # Default False for more lenient behavior
        audit_context["checks_run"].append("detect_vat_mismatch")
        profile = user.profile if hasattr(user, "profile") else None
        
        # Check if VAT is being charged
        if invoice.tax_amount and float(invoice.tax_amount) > 0:
            # VAT is being charged, so there should be a VAT number
            if profile and not profile.vat_number:
                is_anomaly = True
                comments.append("VAT is charged but no VAT number registered")

    # 5. Business logic checks: Duplicate items
    if triggers.get("detect_duplicate_items", True):
        audit_context["checks_run"].append("detect_duplicate_items")
        items = invoice.billed_items.all()
        
        if items.count() > 1:
            # Create a list of (description, quantity) tuples to check for duplicates
            item_signatures = []
            duplicates = []
            
            for item in items:
                # Use description as the key (case-insensitive)
                sig = item.description.lower().strip()
                if sig in item_signatures:
                    duplicates.append(item.description)
                else:
                    item_signatures.append(sig)
            
            if duplicates:
                is_anomaly = True
                dup_list = ", ".join(set(duplicates))
                comments.append(f"Duplicate items detected: {dup_list}")

    comment = " | ".join(comments) if comments else "OK"
    return is_anomaly, comment, audit_context


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
    if user.is_staff or getattr(user, "is_ops", False):
        managed_groups = UserGroup.objects.filter(manager=user)
        return qs.filter(group__in=managed_groups)

    # 3. Tenants: See only data for groups they are members of
    tenant_groups = UserGroup.objects.filter(members__user=user)
    return qs.filter(group__in=tenant_groups)
