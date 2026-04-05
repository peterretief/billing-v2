from items.models import Item
from django.utils import timezone
from django.contrib.auth import get_user_model
from clients.models import Client

# Ensure we're operating within the Django environment if run directly
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_project.settings')
django.setup()

user = get_user_model().objects.get(username='peter')
client = Client.objects.filter(user=user).first()
if client:
    test_item = Item.objects.create(
        user=user,
        client=client,
        description='Test Recurring Item for Timer',
        quantity=1,
        unit_price=50.00,
        date=timezone.now().date(),
        is_billed=False,
        invoice=None,
        billing_policy=None,
        is_recurring=True,
        last_billed_date=timezone.now().date() - timezone.timedelta(days=35) # Set to last month
    )
    print(f"Test recurring item created: ID={test_item.id}")
else:
    print('No client found for user peter')
