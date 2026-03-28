import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'billing_v2.settings')
django.setup()

from django.contrib.auth import get_user_model
from timesheets.models import DefaultWorkCategory, WorkCategory

User = get_user_model()

def sync_user_categories():
    users = User.objects.all()
    created_count = 0
    
    for user in users:
        # Using get_or_create to prevent duplicates if some users already have them
        category, _ = WorkCategory.objects.get_or_create(
            user=user, 
            name="General Work",
            defaults={'description': "Default category for time tracking"}
        )
        
        _, created = DefaultWorkCategory.objects.get_or_create(
            user=user,
            defaults={'work_category': category}
        )
        
        if created:
            created_count += 1

    print(f"✅ Processed all users. Created new defaults for {created_count} users.")

if __name__ == "__main__":
    sync_user_categories()
