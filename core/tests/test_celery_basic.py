from django.test import TestCase
from core_project.celery import app
from decimal import Decimal

@app.task
def add(x, y):
    return x + y

class CeleryBasicTest(TestCase):
    def test_celery_task_runs(self):
        # Synchronous call
        result = add.apply(args=(2, 3)).get()
        self.assertEqual(result, 5)

    def test_celery_task_registered(self):
        self.assertIn('core.tests.test_celery_basic.add', app.tasks)
