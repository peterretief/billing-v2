# delete_duplicate_recurring_items.py
"""
Standalone Django script to delete duplicate recurring items, keeping only one per (user, client, description, unit_price).
Usage:
    python delete_duplicate_recurring_items.py
"""
import os
import django
from collections import defaultdict

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../')

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_project.settings")
django.setup()

from items.models import Item


# Group by (user, client, description, unit_price) for ALL items (recurring and non-recurring)
item_groups = defaultdict(list)
for item in Item.objects.all():
    key = (item.user_id, item.client_id, item.description.strip(), str(item.unit_price))
    item_groups[key].append(item)

total_deleted = 0
for key, items in item_groups.items():
    if len(items) > 1:
        # Sort by created_at, keep the oldest (or change to newest if preferred)
        items_sorted = sorted(items, key=lambda x: x.created_at)
        to_keep = items_sorted[0]
        to_delete = items_sorted[1:]
        ids_to_delete = [i.id for i in to_delete]
        print(f"Keeping item {to_keep.id} for {key}, deleting {ids_to_delete}")
        Item.objects.filter(id__in=ids_to_delete).delete()
        total_deleted += len(ids_to_delete)

print(f"Done. Total duplicate recurring items deleted: {total_deleted}")
