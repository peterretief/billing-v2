from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from timesheets.models import WorkCategory


class Command(BaseCommand):
    help = 'Setup initial work categories'

    def handle(self, *args, **options):
        User = get_user_model()
        # Get your first user (or adjust as needed)
        user = User.objects.first() 
        
        categories = [
            {
                'name': 'Meeting',
                'schema': ['Attendees', 'Meeting_Link', 'Notes']
            },
            {
                'name': 'Site Visit',
                'schema': ['Location', 'Authorized_By', 'Kilometers']
            },
            {
                'name': 'Consulting',
                'schema': ['Project_Phase', 'Stakeholder']
            }
        ]

        for cat in categories:
            obj, created = WorkCategory.objects.get_or_create(
                user=user,
                name=cat['name'],
                defaults={'metadata_schema': cat['schema']}
            )
            status = "Created" if created else "Already exists"
            self.stdout.write(self.style.SUCCESS(f'{status}: {cat["name"]}'))