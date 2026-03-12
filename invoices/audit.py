"""
Invoice Reporting Audit System

This module provides utilities to verify consistency in invoice reporting across
different methods (manager methods, views, reconciliation, etc).

Double-entry verification ensures that:
1. All methods report the same totals
2. Quotes, drafts, and cancelled invoices are handled consistently
3. No data is double-counted or missing
"""

from decimal import Decimal

from django.db.models import Sum

from invoices.models import Invoice, Payment


class InvoiceAudit:
    """
    Audit utility to verify invoice totals are consistent across all reporting methods.
    """
    
    # Rules for what should be included/excluded
    RULES = {
        "BILLED_INVOICES": {
            "exclude_status": ["DRAFT", "CANCELLED"],
            "exclude_is_quote": True,
            "description": "Active invoices (PENDING, OVERDUE, PAID)"
        },
        "OUTSTANDING_INVOICES": {
            "include_status": ["PENDING", "OVERDUE"],
            "exclude_is_quote": True,
            "description": "Unpaid invoices (not PAID, DRAFT, or CANCELLED)"
        },
        "QUOTES_ONLY": {
            "exclude_status": ["CANCELLED"],
            "include_is_quote": True,
            "description": "All quotes except cancelled"
        },
        "PAID_INVOICES": {
            "include_status": ["PAID"],
            "exclude_is_quote": True,
            "description": "Paid invoices only (not quotes)"
        },
        "ALL_TRANSACTIONS": {
            "exclude_status": ["DRAFT"],
            "exclude_is_quote": False,  # Include BOTH invoices and quotes
            "description": "All sent documents (invoices and quotes, but not drafts)"
        }
    }

    def __init__(self, user):
        self.user = user
        self.errors = []
        self.warnings = []

    def verify_billed_invoices(self):
        """
        Verify BILLED total consistency.
        Should be: PENDING + OVERDUE + PAID invoices (NOT quotes, NOT cancelled, NOT draft)
        """
        # Method 1: Using manager .totals()
        manager_total = Invoice.objects.filter(user=self.user).totals()["billed"]
        
        # Method 2: Direct calculation matching the rules
        direct_total = Invoice.objects.filter(
            user=self.user,
            status__in=["PENDING", "OVERDUE", "PAID"]
        ).exclude(is_quote=True).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        # Method 3: Using active() + exclude quotes
        active_total = Invoice.objects.filter(user=self.user).exclude(
            status__in=["DRAFT", "CANCELLED", "PAID"],
            is_quote=True
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        if manager_total != direct_total:
            self.errors.append(
                f"BILLED mismatch: manager={manager_total} vs direct={direct_total}"
            )
        
        return {
            "method": "billed_invoices",
            "manager_total": manager_total,
            "direct_calculation": direct_total,
            "is_consistent": manager_total == direct_total,
        }

    def verify_outstanding_invoices(self):
        """
        Verify OUTSTANDING total consistency.
        Should be: PENDING + OVERDUE invoices minus all payments (NOT quotes, NOT cancelled)
        """
        # Method 1: Using manager .get_total_outstanding()
        manager_outstanding = Invoice.objects.get_total_outstanding(self.user)
        
        # Method 2: Direct calculation
        invoices_total = Invoice.objects.filter(
            user=self.user,
            status__in=["PENDING", "OVERDUE"],
            is_quote=False
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        payments_total = Payment.objects.filter(
            user=self.user
        ).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        
        direct_outstanding = invoices_total - payments_total
        
        if manager_outstanding != direct_outstanding:
            self.errors.append(
                f"OUTSTANDING mismatch: manager={manager_outstanding} vs direct={direct_outstanding} "
                f"(invoices={invoices_total}, payments={payments_total})"
            )
        
        return {
            "method": "outstanding_invoices",
            "manager_outstanding": manager_outstanding,
            "invoices_total": invoices_total,
            "payments_total": payments_total,
            "direct_calculation": direct_outstanding,
            "is_consistent": manager_outstanding == direct_outstanding,
        }

    def verify_quote_exclusion(self):
        """
        Verify that quotes are never included in financial totals.
        """
        # Count quotes
        quote_count = Invoice.objects.filter(
            user=self.user,
            is_quote=True
        ).exclude(status="DRAFT").count()
        
        # Sum of all invoices (with quotes)
        all_total = Invoice.objects.filter(
            user=self.user
        ).exclude(
            status="DRAFT"
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        # Sum without quotes
        invoices_only = Invoice.objects.filter(
            user=self.user
        ).exclude(
            status="DRAFT",
            is_quote=True
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        # The difference should be the quote total
        quote_total = all_total - invoices_only
        
        # Verify manually calculated quote total
        direct_quote_total = Invoice.objects.filter(
            user=self.user,
            is_quote=True
        ).exclude(
            status="DRAFT"
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        if quote_total != direct_quote_total:
            self.warnings.append(
                f"Quote calculation mismatch: derived={quote_total} vs direct={direct_quote_total}"
            )
        
        # Verify manager doesn't include quotes
        manager_billed = Invoice.objects.filter(user=self.user).totals()["billed"]
        if manager_billed == all_total:
            self.errors.append(
                "Manager .totals() appears to include quotes when it shouldn't"
            )
        
        return {
            "method": "quote_exclusion",
            "quote_count": quote_count,
            "all_total_with_quotes": all_total,
            "invoices_only_total": invoices_only,
            "quote_total": quote_total,
            "manager_billed_includes_quotes": manager_billed == all_total,
            "is_consistent": quote_total == direct_quote_total,
        }

    def verify_cancelled_exclusion(self):
        """
        Verify that cancelled invoices are visible but excluded from totals.
        """
        # Count cancelled
        cancelled_count = Invoice.objects.filter(
            user=self.user,
            status="CANCELLED",
            is_quote=False
        ).count()
        
        # Sum including cancelled
        with_cancelled = Invoice.objects.filter(
            user=self.user,
            is_quote=False
        ).exclude(
            status="DRAFT"
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        # Sum excluding cancelled
        without_cancelled = Invoice.objects.filter(
            user=self.user,
            is_quote=False
        ).exclude(
            status__in=["DRAFT", "CANCELLED"]
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        # Manager should match "without cancelled"
        manager_billed = Invoice.objects.filter(user=self.user).totals()["billed"]
        
        if manager_billed != without_cancelled:
            self.errors.append(
                f"CANCELLED exclusion: manager={manager_billed} should exclude cancelled total"
            )
        
        return {
            "method": "cancelled_exclusion",
            "cancelled_count": cancelled_count,
            "total_with_cancelled": with_cancelled,
            "total_without_cancelled": without_cancelled,
            "manager_excluded_cancelled": manager_billed == without_cancelled,
            "is_consistent": manager_billed == without_cancelled,
        }

    def verify_draft_exclusion(self):
        """
        Verify that DRAFT invoices are never included in any totals.
        """
        # Count drafts
        draft_count = Invoice.objects.filter(
            user=self.user,
            status="DRAFT"
        ).count()
        
        # Sum of just sent/active
        sent_total = Invoice.objects.filter(
            user=self.user
        ).exclude(
            status="DRAFT",
            is_quote=True
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0.00")
        
        # Manager should never include drafts
        manager_billed = Invoice.objects.filter(user=self.user).totals()["billed"]
        
        # These should match
        if manager_billed != sent_total:
            self.errors.append(
                f"DRAFT exclusion: manager={manager_billed} vs sent={sent_total}"
            )
        
        return {
            "method": "draft_exclusion",
            "draft_count": draft_count,
            "sent_total_excluding_drafts": sent_total,
            "manager_excluded_drafts": manager_billed == sent_total,
            "is_consistent": manager_billed == sent_total,
        }

    def run_full_audit(self):
        """
        Run all audit checks and return comprehensive report.
        """
        results = {
            "user_id": self.user.id,
            "username": self.user.username,
            "checks": {
                "billed_invoices": self.verify_billed_invoices(),
                "outstanding_invoices": self.verify_outstanding_invoices(),
                "quote_exclusion": self.verify_quote_exclusion(),
                "cancelled_exclusion": self.verify_cancelled_exclusion(),
                "draft_exclusion": self.verify_draft_exclusion(),
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "passed": len(self.errors) == 0,
        }
        
        return results

    def get_summary(self):
        """Get a human-readable summary of the audit."""
        audit_result = self.run_full_audit()
        
        summary_lines = [
            f"Invoice Audit for {audit_result['username']}",
            f"Status: {'PASSED' if audit_result['passed'] else 'FAILED'}",
            f"Errors: {len(audit_result['errors'])}",
            f"Warnings: {len(audit_result['warnings'])}",
            ""
        ]
        
        if audit_result['errors']:
            summary_lines.append("ERRORS:")
            for error in audit_result['errors']:
                summary_lines.append(f"  - {error}")
            summary_lines.append("")
        
        if audit_result['warnings']:
            summary_lines.append("WARNINGS:")
            for warning in audit_result['warnings']:
                summary_lines.append(f"  - {warning}")
            summary_lines.append("")
        
        # Details per check
        summary_lines.append("DETAILS:")
        for check_name, check_result in audit_result['checks'].items():
            consistency = "✓" if check_result.get('is_consistent', False) else "✗"
            summary_lines.append(f"  {consistency} {check_name}")
        
        return "\n".join(summary_lines)
