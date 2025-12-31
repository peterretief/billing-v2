from django.db import migrations
from django.contrib.auth.hashers import make_password

def create_admin_user(apps, schema_editor):
    # Get our Custom User model
    User = apps.get_model('core', 'User')
    
    # Check if it exists first so it doesn't crash on multiple runs
    if not User.objects.filter(username='admin').exists():
        User.objects.create(
            username='admin',
            email='admin@example.com',
            password=make_password('admin123'), # Change this for production!
            is_superuser=True,
            is_staff=True
        )

def remove_admin_user(apps, schema_editor):
    User = apps.get_model('core', 'User')
    User.objects.filter(username='admin').delete()

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'), # Ensure this matches your first migration name
    ]

    operations = [
        migrations.RunPython(create_admin_user, remove_admin_user),
    ]