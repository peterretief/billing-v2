"""
Management command to make existing data comply with new business rules:
1. Auto-create credit notes for CANCELLED invoices that were PAID
2. Report on data integrity issues (payment > invoice amount)
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from invoices.models import CreditNote, Invoice


class Command(BaseCommand):
    help = "Fix existing data to comply with new invoice cancellation and payment rules"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="Only fix invoices for a specific user ID",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        user_id = options.get("user_id")

        self.stdout.write(self.style.SUCCESS("\n" + "="*70))
        self.stdout.write(self.style.SUCCESS("Invoice Compliance Fix Script"))
        self.stdout.write(self.style.SUCCESS("="*70))

        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 DRY RUN MODE - No changes will be made\n"))
        else:
            self.stdout.write(self.style.SUCCESS("✅ Making changes to database\n"))

        # Step 1: Find all CANCELLED invoices that don't have CANCELLATION credits
        self.stdout.write("\n" + "-"*70)
        self.stdout.write("STEP 1: Finding CANCELLED invoices missing credit notes")
        self.stdout.write("-"*70)

        query = Invoice.objects.filter(status=Invoice.Status.CANCELLED)
        if user_id:
            query = query.filter(user_id=user_id)

        cancelled_invoices = query
        total_cancelled = cancelled_invoices.count()
        self.stdout.write(f"Total CANCELLED invoices: {total_cancelled}")

        # Filter to only those that don't have a CANCELLATION credit note
        invoices_needing_credits = []
        for invoice in cancelled_invoices:
            # Check if this invoice has a CANCELLATION credit note
            has_cancellation_credit = CreditNote.objects.filter(
                invoice=invoice,
                note_type=CreditNote.NoteType.CANCELLATION
            ).exists()

            if not has_cancellation_credit and invoice.total_paid > Decimal("0.00"):
                invoices_needing_credits.append(invoice)

        self.stdout.write(
            self.style.WARNING(
                f"Found {len(invoices_needing_credits)} CANCELLED invoices with payments "
                f"but NO credit notes"
            )
        )

        # Step 2: Create credit notes for these invoices
        if invoices_needing_credits:
            self.stdout.write("\n" + "-"*70)
            self.stdout.write("STEP 2: Processing invoices needing credit notes")
            self.stdout.write("-"*70)

            created_count = 0
            error_count = 0

            for invoice in invoices_needing_credits:
                try:
                    currency = invoice.user.profile.currency if hasattr(invoice.user, "profile") else "R"
                    paid_amount = invoice.total_paid

                    msg = (
                        f"\n📋 Invoice {invoice.number}\n"
                        f"   Client: {invoice.client.name}\n"
                        f"   Amount: {currency} {invoice.total_amount}\n"
                        f"   Paid: {currency} {paid_amount}\n"
                        f"   Reason: {invoice.cancellation_reason or 'Not provided'}"
                    )
                    self.stdout.write(msg)

                    if not dry_run:
                        with transaction.atomic():
                            CreditNote.objects.create(
                                user=invoice.user,
                                client=invoice.client,
                                invoice=invoice,
                                note_type=CreditNote.NoteType.CANCELLATION,
                                amount=paid_amount,
                                description=f"Auto-created credit from cancelled invoice {invoice.number}. "
                                           f"Reason: {invoice.cancellation_reason or 'No reason provided'}",
                                reference=f"CN-{invoice.number}"
                            )
                            created_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"   ✅ Credit note created: CN-{invoice.number}")
                            )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"   [DRY RUN] Would create CN-{invoice.number}")
                        )
                        created_count += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"   ❌ Error: {str(e)}"))
                    error_count += 1

            self.stdout.write("\n" + "-"*70)
            self.stdout.write(
                self.style.SUCCESS(f"✅ Created {created_count} credit note(s)")
            )
            if error_count > 0:
                self.stdout.write(
                    self.style.ERROR(f"❌ {error_count} error(s) encountered")
                )

        # Step 3: Check for data integrity issues (payments > invoice amount)
        self.stdout.write("\n" + "-"*70)
        self.stdout.write("STEP 3: Checking for data integrity issues")
        self.stdout.write("-"*70)

        query = Invoice.objects.all()
        if user_id:
            query = query.filter(user_id=user_id)

        integrity_issues = []
        for invoice in query:
            if invoice.total_paid > invoice.total_amount:
                integrity_issues.append(invoice)

        if integrity_issues:
            self.stdout.write(
                self.style.ERROR(
                    f"⚠️  Found {len(integrity_issues)} invoice(s) with overpayments:"
                )
            )

            for invoice in integrity_issues:
                currency = invoice.user.profile.currency if hasattr(invoice.user, "profile") else "R"
                overpayment = invoice.total_paid - invoice.total_amount

                msg = (
                    f"\n  📋 Invoice {invoice.number}\n"
                    f"     Client: {invoice.client.name}\n"
                    f"     Amount: {currency} {invoice.total_amount}\n"
                    f"     Paid: {currency} {invoice.total_paid}\n"
                    f"     Overpayment: {currency} {overpayment}"
                )
                self.stdout.write(self.style.ERROR(msg))
                
                # Show the payments
                payments = invoice.payments.all()
                if payments.exists():
                    self.stdout.write("     Payments:")
                    for payment in payments:
                        self.stdout.write(
                            f"       - {currency} {payment.amount} on {payment.date_paid}"
                        )

        else:
            self.stdout.write(
                self.style.SUCCESS("✅ No data integrity issues found - all invoices compliant!")
            )

        # Step 4: Summary
        self.stdout.write("\n" + "="*70)
        self.stdout.write("SUMMARY")
        self.stdout.write("="*70)

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Would create credit notes for {len(invoices_needing_credits)} invoice(s)"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Created credit notes for {len(invoices_needing_credits)} invoice(s)"))

        if integrity_issues:
            self.stdout.write(
                self.style.ERROR(f"⚠️  {len(integrity_issues)} invoices with overpayments")
            )
            self.stdout.write(self.style.WARNING(
                "  Note: These would violate new business rules. Please review."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("All invoices are compliant with new business rules!"))

        self.stdout.write("\n" + "="*70 + "\n")
