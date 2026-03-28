
from invoices.models import Invoice

from .models import UserGroup


def get_anomaly_status(user, invoice):
    """
    Audits invoices for real data errors WITHOUT blocking operations.
    Logs problematic invoices to dashboard for manual review.
    
    Checks:
    1. Math validation: Does total_amount match sum of line items?
    2. Structural: No items? No total? Duplicate items?
    3. Statistical: Invoice amount unusual relative to history?
    
    Returns tuple: (is_flagged, comment, audit_context)
    - is_flagged: True if issues detected (but never blocks)
    - comment: Human-readable description of issues
    - audit_context: Dict with comparison stats for audit dashboard
    """
    comments = []
    is_flagged = False
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

    # 1. MATH VALIDATION: Does total match sum of line items? *** CATCHES CORRUPTION ***
    if triggers.get("detect_math_error", True):
        audit_context["checks_run"].append("detect_math_error")
        from decimal import Decimal
        
        calculated_sum = Decimal("0.00")
        
        # Add billed items
        if hasattr(invoice, "billed_items") and invoice.billed_items.exists():
            calculated_sum += sum(Decimal(str(item.total)) for item in invoice.billed_items.all())
            
        # Add billed timesheets
        if hasattr(invoice, "billed_timesheets") and invoice.billed_timesheets.exists():
            calculated_sum += sum(Decimal(str(ts.total_value)) for ts in invoice.billed_timesheets.all())
            
        # Add custom lines
        if hasattr(invoice, "custom_lines"):
            calculated_sum += sum(Decimal(str(line.total)) for line in invoice.custom_lines.all())
            
        # Calculate expected total with VAT
        vat_rate = Decimal(str(getattr(profile, "vat_rate", 15.00) or 15.00))
        is_registered = getattr(profile, "is_vat_registered", False)
        
        expected_total = calculated_sum
        if is_registered:
            expected_total += (calculated_sum * (vat_rate / Decimal("100.00")))
            
        # Compare with invoice total (round both to 2 decimal places)
        expected_total = expected_total.quantize(Decimal("0.01"))
        invoice_total = Decimal(str(invoice.total_amount)).quantize(Decimal("0.01"))
        
        if expected_total != invoice_total:
            is_flagged = True
            diff = invoice_total - expected_total
            comments.append(f"❌ MATH ERROR: Line items sum to {expected_total} but total is {invoice_total} (diff: {diff})")

    # 2. STRUCTURAL: Zero or no items — always a problem
    if triggers.get("detect_no_items", True):
        audit_context["checks_run"].append("detect_no_items")
        # Timesheets are items too - check both billed_items AND billed_timesheets
        has_no_items = not invoice.billed_items.exists() and not invoice.billed_timesheets.exists()
        if has_no_items:
            is_flagged = True
            comments.append("❌ STRUCTURE: No line items on invoice")

    if triggers.get("detect_zero_total", True):
        audit_context["checks_run"].append("detect_zero_total")
        zero_total = float(invoice.total_amount) == 0
        if zero_total:
            is_flagged = True
            comments.append("❌ STRUCTURE: Invoice total is zero")

    # 3. STATISTICAL: Unusual amounts relative to user's history (FOR INFORMATION ONLY)
    if triggers.get("detect_statistical_outliers", False):  # Default False - informational only
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
                cv = std_dev / mean if mean > 0 else 0
                audit_context["comparison_cv"] = cv

                current_amount = float(invoice.total_amount)

                # INFO ONLY: Note unusual amounts but don't flag them
                threshold_upper = mean * 10  # 10x average
                threshold_lower = mean * 0.1  # 10% of average

                if current_amount > threshold_upper:
                    ratio = current_amount / mean
                    comments.append(f"ℹ️ WARNING: Invoice is {ratio:.1f}x the average (review if unexpected)")

                if 0 < current_amount < threshold_lower:
                    ratio = current_amount / mean if mean > 0 else 0
                    comments.append(f"ℹ️ WARNING: Invoice is {ratio * 100:.1f}% of average (unusually low)")
        else:
            audit_context["checks_run"].append("insufficient_history")

    # 4. DELIVERY: Check for email delivery failures (bounces, deferred, spam, etc.)
    if triggers.get("detect_email_delivery_failure", False):
        audit_context["checks_run"].append("detect_email_delivery_failure")
        delivery_logs = invoice.delivery_logs.all().values_list('status', flat=True)
        
        if delivery_logs:
            latest_email = invoice.delivery_logs.order_by("-created_at").first()
            # Hard bounce, soft bounce, deferred, spam complaint, unsubscribed
            failed_statuses = ["soft_bounce", "hard_bounce", "bounced", "deferred", "spam", "complaint", "unsubscribed"]
            
            if latest_email.status in failed_statuses:
                is_flagged = True
                # Show if multiple delivery attempts failed
                failure_count = len([s for s in delivery_logs if s in failed_statuses])
                if failure_count > 1:
                    comments.append("❌ EMAIL DELIVERY: HARD BOUNCE - Invalid email address")
                else:
                    comments.append(f"⚠️ EMAIL DELIVERY: {latest_email.status.upper().replace('_', ' ')}")
    
    # 5. DELIVERY: Client email required to send (flag only, won't block creation)
    if triggers.get("detect_missing_email", False):  # Default False
        audit_context["checks_run"].append("detect_missing_email")
        if not invoice.client.email:
            is_flagged = True
            comments.append("⚠️ DELIVERY: Client has no email address (cannot send)")

    # 6. COMPLIANCE: VAT configuration (flag only)
    if triggers.get("detect_vat_mismatch", False):  # Default False
        audit_context["checks_run"].append("detect_vat_mismatch")
        profile = user.profile if hasattr(user, "profile") else None
        
        # Check if VAT is being charged
        if invoice.tax_amount and float(invoice.tax_amount) > 0:
            # VAT is being charged, so there should be a VAT number
            if profile and not profile.vat_number:
                is_flagged = True
                comments.append("⚠️ COMPLIANCE: VAT is charged but no VAT number registered")

    # 6. QUALITY: Duplicate items (flag only)
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
                is_flagged = True
                dup_list = ", ".join(set(duplicates))
                comments.append(f"⚠️ QUALITY: Possible duplicate items: {dup_list}")

    comment = " | ".join(comments) if comments else "✓ OK"
    return is_flagged, comment, audit_context


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
    if user.is_staff:
        managed_groups = UserGroup.objects.filter(manager=user)
        return qs.filter(group__in=managed_groups)

    # 3. Tenants: See only data for groups they are members of
    tenant_groups = UserGroup.objects.filter(members__user=user)
    return qs.filter(group__in=tenant_groups)
