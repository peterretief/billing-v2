from django.contrib.auth import get_user_model
from django.test import TestCase

from timesheets.models import DefaultWorkCategory, WorkCategory

User = get_user_model()


class DefaultCategorySignalTest(TestCase):
    def setUp(self):
        # Ensure there are some default categories
        DefaultWorkCategory.objects.all().delete()
        DefaultWorkCategory.objects.create(name="Dev")
        DefaultWorkCategory.objects.create(name="Design")
        DefaultWorkCategory.objects.create(name="Meetings")

    def test_new_user_gets_default_categories(self):
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        # Should have all default categories
        user_cats = WorkCategory.objects.filter(user=user)
        default_names = set(DefaultWorkCategory.objects.values_list("name", flat=True))
        user_names = set(user_cats.values_list("name", flat=True))
        self.assertEqual(default_names, user_names)
        self.assertTrue(user_cats.count() > 0)
