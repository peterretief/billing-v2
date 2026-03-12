from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client
from timesheets.models import WorkCategory

from .models import Todo

User = get_user_model()


class TodoModelTests(TestCase):
    """Test Todo model functionality."""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client = Client.objects.create(
            user=self.user,
            name='Test Client',
            email='client@test.com'
        )
        self.category = WorkCategory.objects.create(
            user=self.user,
            name='Test Task'
        )
    
    def test_create_todo(self):
        """Test creating a todo."""
        todo = Todo.objects.create(
            user=self.user,
            client=self.client,
            category=self.category,
            description='Test Description'
        )
        self.assertEqual(todo.category.name, 'Test Task')
        self.assertEqual(todo.status, Todo.Status.TODO)
    
    def test_mark_completed(self):
        """Test marking todo as completed."""
        category = WorkCategory.objects.create(
            user=self.user,
            name='Complete Me'
        )
        todo = Todo.objects.create(
            user=self.user,
            client=self.client,
            category=category
        )
        todo.mark_completed()
        self.assertEqual(todo.status, Todo.Status.COMPLETED)
        self.assertIsNotNone(todo.completed_at)
    
    def test_is_overdue(self):
        """Test overdue detection."""
        past_date = timezone.now().date() - timezone.timedelta(days=1)
        future_date = timezone.now().date() + timezone.timedelta(days=1)
        
        # Overdue todo
        overdue_cat = WorkCategory.objects.create(user=self.user, name='Overdue')
        overdue = Todo.objects.create(
            user=self.user,
            client=self.client,
            category=overdue_cat,
            due_date=past_date,
            status=Todo.Status.TODO
        )
        self.assertTrue(overdue.is_overdue)
        
        # Not overdue todo
        upcoming_cat = WorkCategory.objects.create(user=self.user, name='Upcoming')
        upcoming = Todo.objects.create(
            user=self.user,
            client=self.client,
            category=upcoming_cat,
            due_date=future_date
        )
        self.assertFalse(upcoming.is_overdue)
