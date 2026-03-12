"""
Management command to test and display the client summary dashboard data.
Useful for debugging and verifying the summary calculations.

Usage:
    python manage.py test_client_summary [--user USERNAME] [--client-id ID]
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from clients.models import Client
from clients.summary import AllClientsSummary, ClientSummary

User = get_user_model()


class Command(BaseCommand):
    help = "Display client summary data for testing and debugging"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            help="Username to test summary for",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            help="Client ID to display summary for",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Display summary for all users",
        )

    def handle(self, *args, **options):
        if options.get("client_id"):
            # Display summary for a single client
            try:
                client = Client.objects.get(pk=options["client_id"])
                self.display_client_summary(client)
            except Client.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Client with ID {options['client_id']} not found"))

        elif options.get("user"):
            # Display summary for a specific user
            try:
                user = User.objects.get(username=options["user"])
                self.display_all_clients_summary(user)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User {options['user']} not found"))

        elif options.get("all"):
            # Display summary for all users
            for user in User.objects.all():
                self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
                self.stdout.write(self.style.SUCCESS(f"User: {user.username}"))
                self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
                self.display_all_clients_summary(user)

        else:
            self.stdout.write(self.style.WARNING("Please specify --user, --client-id, or --all"))

    def display_client_summary(self, client):
        """Display summary for a single client"""
        self.stdout.write(self.style.SUCCESS(f"\nClient Summary: {client.name}"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        summary = ClientSummary(client).get_summary()

        # Quotes
        self.stdout.write("\n[QUOTES]")
        self.stdout.write(f"  Pending:  {summary['quotes']['pending']['count']} items - ${summary['quotes']['pending']['total']:.2f}")
        self.stdout.write(f"  Accepted: {summary['quotes']['accepted']['count']} items - ${summary['quotes']['accepted']['total']:.2f}")
        self.stdout.write(f"  Rejected: {summary['quotes']['rejected']['count']} items - ${summary['quotes']['rejected']['total']:.2f}")
        self.stdout.write(f"  TOTAL:    {summary['quotes']['total_count']} items - ${summary['quotes']['total_value']:.2f}")

        # Timesheets
        self.stdout.write("\n[TIMESHEETS]")
        self.stdout.write(f"  Billed:   {summary['timesheets']['billed']['count']} entries ({summary['timesheets']['billed']['hours']:.2f} hrs) - ${summary['timesheets']['billed']['total']:.2f}")
        self.stdout.write(f"  Unbilled: {summary['timesheets']['unbilled']['count']} entries ({summary['timesheets']['unbilled']['hours']:.2f} hrs) - ${summary['timesheets']['unbilled']['total']:.2f}")
        self.stdout.write(f"  TOTAL:    {summary['timesheets']['total_count']} entries ({summary['timesheets']['total_hours']:.2f} hrs) - ${summary['timesheets']['total_value']:.2f}")

        # Items
        self.stdout.write("\n[ITEMS]")
        self.stdout.write(f"  Billed:   {summary['items']['billed']['count']} items - ${summary['items']['billed']['total']:.2f}")
        self.stdout.write(f"  Unbilled: {summary['items']['unbilled']['count']} items - ${summary['items']['unbilled']['total']:.2f}")
        self.stdout.write(f"  TOTAL:    {summary['items']['total_count']} items - ${summary['items']['total_value']:.2f}")

        # Invoices
        self.stdout.write("\n[INVOICES]")
        self.stdout.write(f"  Draft:    {summary['invoices']['draft']['count']} items - ${summary['invoices']['draft']['total']:.2f}")
        self.stdout.write(f"  Pending:  {summary['invoices']['pending']['count']} items - ${summary['invoices']['pending']['total']:.2f}")
        self.stdout.write(f"  Overdue:  {summary['invoices']['overdue']['count']} items - ${summary['invoices']['overdue']['total']:.2f}")
        self.stdout.write(f"  Paid:     {summary['invoices']['paid']['count']} items - ${summary['invoices']['paid']['total']:.2f}")
        self.stdout.write(f"  Cancelled:{summary['invoices']['cancelled']['count']} items - ${summary['invoices']['cancelled']['total']:.2f}")
        self.stdout.write(f"  TOTAL:    {summary['invoices']['total_count']} items - ${summary['invoices']['total_value']:.2f}")

        # Email Status
        self.stdout.write("\n[EMAIL STATUS]")
        self.stdout.write(f"  Emailed:     {summary['email_status']['emailed']['count']} items - ${summary['email_status']['emailed']['total']:.2f}")
        self.stdout.write(f"  Not Emailed: {summary['email_status']['not_emailed']['count']} items - ${summary['email_status']['not_emailed']['total']:.2f}")

        # Outstanding
        self.stdout.write("\n[OUTSTANDING]")
        self.stdout.write(f"  Count:  {summary['outstanding']['count']} invoices")
        self.stdout.write(f"  Total:  ${summary['outstanding']['total']:.2f}")

    def display_all_clients_summary(self, user):
        """Display summary for all clients of a user"""
        all_summaries = AllClientsSummary(user)
        summaries = all_summaries.get_all_summaries()
        totals = all_summaries.get_totals()

        self.stdout.write(f"\nTotal Clients: {totals['clients_count']}")
        self.stdout.write(f"Total Quotes: {totals['quotes_total_count']} items - ${totals['quotes_total_value']:.2f}")
        self.stdout.write(f"Total Timesheets: {totals['timesheets_total_count']} entries ({totals['timesheets_total_hours']:.2f} hrs) - ${totals['timesheets_total_value']:.2f}")
        self.stdout.write(f"Total Items: {totals['items_total_count']} items - ${totals['items_total_value']:.2f}")
        self.stdout.write(f"Total Invoices: {totals['invoices_total_count']} items - ${totals['invoices_total_value']:.2f}")
        self.stdout.write(f"Total Outstanding: ${totals['outstanding_total']:.2f}")

        # Display individual clients
        self.stdout.write("\n" + "=" * 100)
        self.stdout.write(f"{'Client':<30} {'Quotes':>15} {'Timesheets':>15} {'Items':>15} {'Invoices':>15} {'Outstanding':>15}")
        self.stdout.write("=" * 100)

        for summary in summaries:
            client = summary["client"]
            quotes = summary["quotes"]["total_value"]
            timesheets = summary["timesheets"]["total_value"]
            items = summary["items"]["total_value"]
            invoices = summary["invoices"]["total_value"]
            outstanding = summary["outstanding"]["total"]

            self.stdout.write(
                f"{client.name:<30} ${quotes:>14.2f} ${timesheets:>14.2f} ${items:>14.2f} ${invoices:>14.2f} ${outstanding:>14.2f}"
            )
