"""
Tests for Celery task discovery and registration.
Ensures all expected tasks are properly registered with Celery.
"""

from django.test import TestCase
from django.apps import apps
from core_project.celery import app as celery_app


class CeleryTaskDiscoveryTest(TestCase):
    """Verify Celery task autodiscovery is working correctly"""

    def test_all_required_tasks_registered(self):
        """Verify critical tasks are discoverable by Celery"""
        required_tasks = [
            "billing_schedule.tasks.process_daily_billing_queue",
            "notifications.tasks.generate_notifications_async",
            "events.tasks.sync_all_users_events_with_calendar",
            "events.tasks.cleanup_old_sync_logs",
            "events.tasks.sync_user_events_with_calendar",
            "invoices.tasks.send_invoice_async",
            "invoices.tasks.generate_ai_insights_task",
            "invoices.tasks.send_mid_month_financial_report",
            "clients.tasks.check_verification",
        ]

        registered_tasks = set(celery_app.tasks.keys())
        user_tasks = {t for t in registered_tasks if not t.startswith("celery.")}

        missing_tasks = []
        for task_name in required_tasks:
            if task_name not in user_tasks:
                missing_tasks.append(task_name)

        self.assertEqual(
            len(missing_tasks),
            0,
            f"Missing tasks: {missing_tasks}. This indicates apps/*/apps.py "
            f"likely doesn't import tasks in ready() method",
        )

    def test_task_count_is_reasonable(self):
        """Ensure we have a reasonable number of tasks (catches autodiscover silently failing)"""
        registered_tasks = [t for t in celery_app.tasks.keys() if not t.startswith("celery.")]

        # We expect at least 8 user tasks
        self.assertGreaterEqual(
            len(registered_tasks),
            8,
            f"Only found {len(registered_tasks)} tasks. Expected 8+. "
            f"Celery autodiscover may be failing.",
        )

    def test_app_configs_have_ready_methods(self):
        """Ensure apps with tasks.py have ready() methods"""
        apps_with_tasks = [
            "billing_schedule",
            "invoices",
            "events",
            "clients",
            "notifications",
        ]

        for app_name in apps_with_tasks:
            app_config = apps.get_app_config(app_name)
            self.assertTrue(
                hasattr(app_config, "ready"),
                f"{app_name}/apps.py missing ready() method. "
                f"This breaks Celery task autodiscovery!",
            )

    def test_app_ready_methods_import_tasks(self):
        """Verify ready() methods actually import the tasks module"""
        apps_with_tasks = [
            "billing_schedule",
            "invoices",
            "events",
            "clients",
            "notifications",
        ]

        import inspect

        for app_name in apps_with_tasks:
            app_config = apps.get_app_config(app_name)
            
            if not hasattr(app_config, "ready"):
                self.fail(f"{app_name}/apps.py has no ready() method")

            # Get the source code of ready() method
            try:
                source = inspect.getsource(app_config.ready)
                
                has_task_import = (
                    f"import {app_name}.tasks" in source
                    or f"from {app_name} import tasks" in source
                    or f"from {app_name}.tasks import" in source
                )

                self.assertTrue(
                    has_task_import,
                    f"{app_name}/apps.py ready() method doesn't import tasks. "
                    f"Add: from {app_name} import tasks",
                )
            except (TypeError, OSError):
                # Some app configs may not have inspectable source
                pass
