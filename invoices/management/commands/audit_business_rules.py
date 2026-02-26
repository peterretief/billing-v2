"""
Audit script to check entire app for inconsistencies with new business rules:
1. Payments should never exceed invoice amounts
2. PAID invoices cancelled should have credit notes
3. No payments allowed on DRAFT/CANCELLED invoices
4. All financial data integrity checks
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum, Q
from decimal import Decimal

from invoices.models import Invoice, Payment, CreditNote
from clients.models import Client


class Command(BaseCommand):
    help = "Audit entire app for business rule violations and data inconsistencies"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            help="Only audit invoices for a specific user ID",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            help="Only audit invoices for a specific client ID",
        )

    def handle(self, *args, **options):
        user_id = options.get("user_id")
        client_id = options.get("client_id")

        self.stdout.write(self.style.SUCCESS("\n" + "="*80))
        self.stdout.write(self.style.SUCCESS("BUSINESS RULES AUDIT REPORT"))
        self.stdout.write(self.style.SUCCESS("="*80 + "\n"))

        # Initialize issue counters
        issues = {
            "overpayments": [],
            "payments_on_draft": [],
            "payments_on_cancelled": [],
            "missing_cancellation_credits": [],
            "orphaned_credits": [],
        }

        # Get invoices to audit
        query = Invoice.objects.all()
        if user_id:
            query = query.filter(user_id=user_id)
        if client_id:
            query = query.filter(client_id=client_id)

        total_invoices = query.count()
        self.stdout.write(f"Auditing {total_invoices} invoices...\n")

        # ============================================================
        # RULE 1: Check for payments on DRAFT invoices
        # ============================================================
        self.stdout.write(self.style.WARNING("RULE 1: Payments on DRAFT invoices"))
        self.stdout.write("-" * 80)

        draft_with_payments = query.filter(status=Invoice.Status.DRAFT).filter(
            payments__isnull=False
        ).distinct()

        if draft_with_payments.exists():
            self.stdout.write(self.style.ERROR(f"  ❌ Found {draft_with_payments.count()} DRAFT invoices with payments:"))
            for inv in draft_with_payments:
                payments = inv.payments.all()
                total = sum(p.amount for p in payments)
                self.stdout.write(
                    self.style.ERROR(
                        f"    • {inv.number} ({inv.status}): R {total} paid"
                    )
                )
                issues["payments_on_draft"].append(inv)
        else:
            self.stdout.write(self.style.SUCCESS("  ✅ PASS: No payments on DRAFT invoices"))

        # ============================================================
        # RULE 2: Check for payments on CANCELLED invoices
        # ============================================================
        self.stdout.write("\n" + self.style.WARNING("RULE 2: Payments on CANCELLED invoices"))
        self.stdout.write("-" * 80)

        cancelled_with_payments = query.filter(status=Invoice.Status.CANCELLED).filter(
            payments__isnull=False
        ).distinct()

        if cancelled_with_payments.exists():
            self.stdout.write(
                self.style.ERROR(f"  ❌ Found {cancelled_with_payments.count()} CANCELLED invoices with payments:")
            )
            for inv in cancelled_with_payments:
                payments = inv.payments.all()
                total = sum(p.amount for p in payments)
                self.stdout.write(
                    self.style.ERROR(
                        f"    • {inv.number} ({inv.status}): R {total} paid"
                    )
                )
                issues["payments_on_cancelled"].append(inv)
        else:
            self.stdout.write(self.style.SUCCESS("  ✅ PASS: No payments on CANCELLED invoices"))

        # ============================================================
        # RULE 3: Check for overpayments (total_paid > total_amount)
        # ============================================================
        self.stdout.write("\n" + self.style.WARNING("RULE 3: Overpayments (paid > invoice amount)"))
        self.stdout.write("-" * 80)

        overpayment_invoices = []
        for inv in query:
            if inv.total_paid > inv.total_amount:
                overpayment_invoices.append(inv)

        if overpayment_invoices:
            self.stdout.write(
                self.style.ERROR(f"  ❌ Found {len(overpayment_invoices)} invoices with overpayments:")
            )
            for inv in overpayment_invoices:
                overpayment = inv.total_paid - inv.total_amount
                self.stdout.write(
                    self.style.ERROR(
                        f"    • {inv.number}: Paid R {inv.total_paid} vs Amount R {inv.total_amount} "
                        f"(overpayment: R {overpayment})"
                    )
                )
                issues["overpayments"].append(inv)
        else:
            self.stdout.write(self.style.SUCCESS("  ✅ PASS: No overpayments found"))

        # ============================================================
        # RULE 4: Check for PAID→CANCELLED without credit notes
        # ============================================================
        self.stdout.write("\n" + self.style.WARNING("RULE 4: PAID→CANCELLED transitions without credit notes"))
        self.stdout.write("-" * 80)

        # We check cancelled invoices that HAD payments but no cancellation credit
        # This is harder without history, but we can look for patterns
        cancelled_invoices = query.filter(status=Invoice.Status.CANCELLED)
        missing_credits = []

        for inv in cancelled_invoices:
            # If this cancelled invoice has a total_paid > 0, it should have a CANCELLATION credit
            if inv.total_paid > Decimal("0.00"):
                has_cancellation_credit = CreditNote.objects.filter(
                    invoice=inv,
                    note_type=CreditNote.NoteType.CANCELLATION
                ).exists()

                if not has_cancellation_credit:
                    missing_credits.append(inv)

        if missing_credits:
            self.stdout.write(
                self.style.ERROR(f"  ❌ Found {len(missing_credits)} CANCELLED invoices with payments but NO credit notes:")
            )
            for inv in missing_credits:
                self.stdout.write(
                    self.style.ERROR(
                        f"    • {inv.number}: Paid R {inv.total_paid}, no cancellation credit"
                    )
                )
                issues["missing_cancellation_credits"].append(inv)
        else:
            self.stdout.write(self.style.SUCCESS("  ✅ PASS: All PAID→CANCELLED invoices have credit notes"))

        # ============================================================
        # Check 5: Orphaned credit notes (no related invoice)
        # ============================================================
        self.stdout.write("\n" + self.style.WARNING("CHECK 5: Orphaned credit notes (client-level only)"))
        self.stdout.write("-" * 80)

        if client_id:
            orphaned = CreditNote.objects.filter(client_id=client_id, invoice__isnull=True)
            if orphaned.exists():
                self.stdout.write(
                    self.style.WARNING(f"  ⚠️  Found {orphaned.count()} client-level credit notes (not tied to invoices):")
                )
                for c in orphaned:
                    self.stdout.write(
                        f"    • {c.reference}: R {c.amount} ({c.note_type})"
                    )
                    issues["orphaned_credits"].append(c)
            else:
                self.stdout.write(self.style.SUCCESS("  ✅ PASS: No orphaned credit notes"))

        # ============================================================
        # SUMMARY
        # ============================================================
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS("AUDIT SUMMARY"))
        self.stdout.write("="*80)

        total_issues = sum(len(v) for v in issues.values() if isinstance(v, list))

        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS(f"\n✅ NO ISSUES FOUND - All {total_invoices} invoices are compliant!\n"))
        else:
            self.stdout.write(self.style.ERROR(f"\n❌ FOUND {total_issues} ISSUES:\n"))

            if issues["payments_on_draft"]:
                self.stdout.write(
                    self.style.ERROR(f"  • Payments on DRAFT invoices: {len(issues['payments_on_draft'])}")
                )
            if issues["payments_on_cancelled"]:
                self.stdout.write(
                    self.style.ERROR(f"  • Payments on CANCELLED invoices: {len(issues['payments_on_cancelled'])}")
                )
            if issues["overpayments"]:
                self.stdout.write(
                    self.style.ERROR(f"  • Overpayments (paid > amount): {len(issues['overpayments'])}")
                )
            if issues["missing_cancellation_credits"]:
                self.stdout.write(
                    self.style.ERROR(
                        f"  • PAID→CANCELLED missing credits: {len(issues['missing_cancellation_credits'])}"
                    )
                )
            if issues["orphaned_credits"]:
                self.stdout.write(
                    self.style.WARNING(f"  • Orphaned credit notes: {len(issues['orphaned_credits'])}")
                )

        self.stdout.write("\n" + "="*80 + "\n")

        # ============================================================
        # STATISTICS
        # ============================================================
        self.stdout.write(self.style.SUCCESS("STATISTICS"))
        self.stdout.write("-" * 80)

        total_paid_all = sum(p.amount for p in Payment.objects.filter(invoice__in=query))
        total_invoiced = sum(inv.total_amount for inv in query if inv.status != Invoice.Status.CANCELLED)
        total_credits = sum(c.amount for c in CreditNote.objects.filter(invoice__in=query))

        self.stdout.write(f"  Total invoices audited: {total_invoices}")
        self.stdout.write(f"  Total invoiced amount: R {total_invoiced}")
        self.stdout.write(f"  Total payments recorded: R {total_paid_all}")
        self.stdout.write(f"  Total credits issued: R {total_credits}")

        # Group by status
        by_status = {}
        for status in Invoice.Status.choices:
            count = query.filter(status=status[0]).count()
            if count > 0:
                by_status[status[1]] = count

        self.stdout.write(f"\n  By Status:")
        for status, count in by_status.items():
            self.stdout.write(f"    • {status}: {count}")

        self.stdout.write("\n" + "="*80 + "\n")
