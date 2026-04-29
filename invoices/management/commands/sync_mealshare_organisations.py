"""
Management command to sync MealShare organisations from Supabase to billing_v2 Clients.

Usage:
    python manage.py sync_mealshare_organisations
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import User
from clients.models import Client
import os

try:
    from supabase import create_client
except ImportError:
    print("Warning: supabase-py not installed. Install with: pip install supabase")
    SUPABASE_AVAILABLE = False
else:
    SUPABASE_AVAILABLE = True


class Command(BaseCommand):
    help = 'Sync MealShare organisations from Supabase to billing_v2 Clients'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org-id',
            type=str,
            help='Sync a specific organisation by ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not SUPABASE_AVAILABLE:
            self.stdout.write(
                self.style.ERROR(
                    'supabase-py is not installed. Install with: pip install supabase'
                )
            )
            return

        # Get Supabase config from environment
        supabase_url = os.getenv('NEXT_PUBLIC_SUPABASE_URL', 'http://192.168.0.102:8000')
        supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

        if not supabase_key:
            self.stdout.write(
                self.style.ERROR('SUPABASE_SERVICE_ROLE_KEY not set in environment')
            )
            return

        # Connect to Supabase
        supabase = create_client(supabase_url, supabase_key)

        # Get or create default user for synced organisations
        sync_user, _ = User.objects.get_or_create(
            username='mealshare_sync',
            defaults={
                'email': 'sync@mealshare.local',
                'first_name': 'MealShare',
                'last_name': 'Sync',
            }
        )

        try:
            # Fetch organisations from MealShare
            if options['org_id']:
                response = supabase.table('organisations').select('*').eq('id', options['org_id']).execute()
            else:
                response = supabase.table('organisations').select('*').execute()

            organisations = response.data

            if not organisations:
                self.stdout.write(self.style.WARNING('No organisations found in MealShare'))
                return

            synced_count = 0
            created_count = 0

            for org in organisations:
                org_id = org['id']
                org_name = org.get('name', 'MealShare Organisation')

                # Check if client already exists by external_id
                try:
                    client = Client.objects.get(external_id=org_id)
                    created = False
                    # Update name if changed
                    if client.name != org_name:
                        if not options['dry_run']:
                            client.name = org_name
                            client.save()
                        status = '✓ UPDATED'
                    else:
                        status = '○ EXISTS'
                except Client.DoesNotExist:
                    # Create new client
                    if not options['dry_run']:
                        client = Client.objects.create(
                            user=sync_user,
                            external_id=org_id,
                            name=org_name,
                            email=org.get('email', f'{org_id[:8]}@mealshare.local'),
                            contact_name=org.get('contact_name', ''),
                            payment_terms=30,
                        )
                    created = True
                    status = '✓ CREATED'

                if created:
                    created_count += 1

                synced_count += 1
                prefix = '[DRY-RUN] ' if options['dry_run'] else ''
                self.stdout.write(
                    f'{prefix}{status}: {org_name} ({org_id[:8]}...)'
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Synced {synced_count} organisations '
                    f'({created_count} new, {synced_count - created_count} existing)'
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error syncing organisations: {str(e)}')
            )
