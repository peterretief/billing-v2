# Generated migration for Events app
import django.contrib.auth.models
import django.contrib.postgres.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('timesheets', '0004_defaultworkcategory'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('clients', '0005_add_client_uuid'),
    ]

    operations = [
        migrations.CreateModel(
            name='GoogleCalendarCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_token', models.TextField()),
                ('refresh_token', models.TextField(blank=True, null=True)),
                ('token_expiry', models.DateTimeField(blank=True, null=True)),
                ('sync_enabled', models.BooleanField(default=True)),
                ('calendar_id', models.CharField(blank=True, max_length=255, null=True)),
                ('email_address', models.EmailField(blank=True, max_length=254, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_related', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Google Calendar Credential',
                'verbose_name_plural': 'Google Calendar Credentials',
                'db_table': 'todos_googlecalendarcredential',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('backlog', 'Backlog'), ('todo', 'To Do'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='todo', max_length=20)),
                ('priority', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='medium', max_length=20)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('suggested_start_time', models.DateTimeField(blank=True, help_text='Suggested start time from slot finder (used for calendar sync)', null=True)),
                ('google_calendar_event_id', models.CharField(blank=True, help_text='Google Calendar event ID (to prevent duplicates)', max_length=255, null=True)),
                ('synced_to_calendar', models.BooleanField(default=False, help_text='Marked as synced to Google Calendar')),
                ('estimated_hours', models.DecimalField(blank=True, decimal_places=2, help_text='Estimated hours to complete this task', max_digits=6, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('category', models.ForeignKey(blank=True, help_text='Work category for this task', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='events', to='timesheets.workcategory')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='clients.client')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_related', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Event',
                'verbose_name_plural': 'Events',
                'db_table': 'todos_todo',
                'ordering': ['-created_at'],
                'managed': False,
            },
        ),
    ]
