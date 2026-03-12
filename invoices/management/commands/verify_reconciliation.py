"""
Management command to verify reconciliation calculations and identify data issues.

Usage:
    python manage.py verify_reconciliation --client ID [--user USERNAME] [--start-date DATE] [--end-date DATE]
    python manage.py verify_reconciliation --all-clients --user USERNAME
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from clients.models import Client
from invoices.reconciliation import ClientReconciliation

User = get_user_model()


class Command(BaseCommand):
    help = "Verify reconciliation calculations using dual verification"

    def add_arguments(self, parser):
        parser.add_argument("--client", type=int, help="Client ID to verify")
        parser.add_argument("--user", type=str, help="Username to verify")
        parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
        parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
        parser.add_argument("--all-clients", action="store_true", help="Verify all clients")
        parser.add_argument("--verbose", action="store_true", help="Show detailed verification steps")

    def handle(self, *args, **options):
        if options.get("client"):
            self.verify_single_client(options)
        elif options.get("all_clients") and options.get("user"):
            self.verify_all_clients(options)
        else:
            self.stdout.write(self.style.WARNING("Please specify --client <ID> or --all-clients"))

    def verify_single_client(self, options):
        """Verify reconciliation for a single client."""
        try:
            client = Client.objects.get(pk=options["client"])
        except Client.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Client {options['client']} not found"))
            return

        if options.get("user"):
            try:
                user = User.objects.get(username=options["user"])
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User {options['user']} not found"))
                return
        else:
            user = client.user

        # Parse dates
        start_date = None
        end_date = date.today()

        if options.get("start_date"):
            try:
                start_date = date.fromisoformat(options["start_date"])
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid start date: {options['start_date']}"))
                return

        if options.get("end_date"):
            try:
                end_date = date.fromisoformat(options["end_date"])
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid end date: {options['end_date']}"))
                return

        # Run verification
        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS(f"Verifying: {client.name}"))
        self.stdout.write(self.style.SUCCESS(f"User: {user.username}"))
        if start_date:
            self.stdout.write(self.style.SUCCESS(f"Period: {start_date} to {end_date}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Period: From beginning to {end_date}"))
        self.stdout.write(self.style.SUCCESS(f"{'='*80}\n"))

        recon = ClientReconciliation(client, user, start_date, end_date)
        report = recon.get_full_report()

        # Display verification status
        if report["has_verification_errors"]:
            self.stdout.write(self.style.ERROR("❌ VERIFICATION FAILED"))
            self.stdout.write("\n" + self.style.ERROR("Errors Found:"))
            for error in report["verification_errors"]:
                self.stdout.write(self.style.ERROR(f"  {error}\n"))
        else:
            self.stdout.write(self.style.SUCCESS("✓ VERIFICATION PASSED"))

        # Display summary
        self.stdout.write("\n" + self.style.SUCCESS("Summary:"))
        summary = report["summary"]
        self.stdout.write(f"  Opening Balance:        {summary['opening_balance']:>12.2f}")
        self.stdout.write(f"  + Invoices Sent:        {summary['invoices_sent']:>12.2f}")
        self.stdout.write(f"  - Invoices Cancelled:   {summary['invoices_cancelled']:>12.2f}")
        self.stdout.write(f"  - Payments (Cash):      {summary['payments_received']:>12.2f}")
        self.stdout.write(f"  - Credit Applied:       {summary['credit_in_payments']:>12.2f}")
        self.stdout.write(f"  - Credit Notes Issued:  {summary['credit_notes_issued']:>12.2f}")
        self.stdout.write(f"  {'─'*40}")
        self.stdout.write(f"  = Closing Balance:      {summary['closing_balance']:>12.2f}")

        self.stdout.write(f"\n  Transactions: {summary['transaction_count']}\n")

        # Verbose output: show all data
        if options.get("verbose"):
            self.stdout.write(self.style.SUCCESS("\nDetailed Transactions:"))
            for trans in report["transactions"]:
                self.stdout.write(
                    f"  {trans['date']} {trans['type']:20} "
                    f"{trans['description']:40} {trans['amount']:>12.2f} → {trans['running_balance']:>12.2f}"
                )

    def verify_all_clients(self, options):
        """Verify reconciliation for all clients of a user."""
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User {options['user']} not found"))
            return

        clients = Client.objects.filter(user=user).order_by("name")

        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS(f"Verifying all clients for: {user.username}"))
        self.stdout.write(self.style.SUCCESS(f"Total clients: {clients.count()}"))
        self.stdout.write(self.style.SUCCESS(f"{'='*80}\n"))

        failed = []
        passed = []

        for client in clients:
            recon = ClientReconciliation(client, user)
            report = recon.get_full_report()

            status = "✓" if not report["has_verification_errors"] else "✗"
            summary = report["summary"]
            balance = summary["closing_balance"]

            self.stdout.write(f"{status} {client.name:<40} Balance: {balance:>12.2f}")

            if report["has_verification_errors"]:
                failed.append((client.name, report["verification_errors"]))
                for error in report["verification_errors"]:
                    self.stdout.write(self.style.ERROR(f"    ERROR: {error}\n"))
            else:
                passed.append(client.name)

        # Summary
        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS(f"Results: {len(passed)} passed, {len(failed)} failed"))
        self.stdout.write(self.style.SUCCESS(f"{'='*80}\n"))

        if failed:
            self.stdout.write(self.style.ERROR("Failed Clients:"))
            for name, errors in failed:
                self.stdout.write(self.style.ERROR(f"  • {name}"))
                for error in errors:
                    self.stdout.write(self.style.ERROR(f"      {error[:100]}..."))
