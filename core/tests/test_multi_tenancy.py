from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from invoices.models import Invoice
from clients.models import Client
from datetime import date, timedelta
from core.current_user import set_current_user, clear_current_user
from core.middleware import TenantMiddleware

User = get_user_model()

class MultiTenancyTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="user1", email="user1@example.com", password="password")
        self.user2 = User.objects.create_user(username="user2", email="user2@example.com", password="password")
        
        self.client1 = Client.objects.create(user=self.user1, name="Client 1", client_code="C1")
        self.client2 = Client.objects.create(user=self.user2, name="Client 2", client_code="C2")
        
        self.invoice1 = Invoice.objects.create(
            user=self.user1,
            client=self.client1,
            number="INV-001",
            due_date=date.today() + timedelta(days=14)
        )
        self.invoice2 = Invoice.objects.create(
            user=self.user2,
            client=self.client2,
            number="INV-002",
            due_date=date.today() + timedelta(days=14)
        )
        self.factory = RequestFactory()

    def tearDown(self):
        clear_current_user()

    def test_for_user_filter(self):
        """Verify that .for_user(user) correctly filters data."""
        user1_invoices = Invoice.objects.for_user(self.user1)
        self.assertEqual(user1_invoices.count(), 1)
        self.assertEqual(user1_invoices.first(), self.invoice1)
        
        user2_invoices = Invoice.objects.for_user(self.user2)
        self.assertEqual(user2_invoices.count(), 1)
        self.assertEqual(user2_invoices.first(), self.invoice2)

    def test_automatic_filtering_via_middleware(self):
        """
        Verify that TenantMiddleware sets the current user and 
        objects.all() is automatically filtered.
        """
        request = self.factory.get("/")
        request.user = self.user1
        
        results = {}
        def get_response(req):
            results['count'] = Invoice.objects.all().count()
            results['first'] = Invoice.objects.all().first()
            return None

        middleware = TenantMiddleware(get_response=get_response)
        middleware(request)
        
        # Inside the middleware, objects.all() should only show user1's invoices
        self.assertEqual(results['count'], 1)
        self.assertEqual(results['first'], self.invoice1)

    def test_automatic_filtering_for_user2(self):
        """Verify automatic filtering works for another user."""
        request = self.factory.get("/")
        request.user = self.user2
        
        results = {}
        def get_response(req):
            results['count'] = Invoice.objects.all().count()
            results['first'] = Invoice.objects.all().first()
            return None

        middleware = TenantMiddleware(get_response=get_response)
        middleware(request)
        
        self.assertEqual(results['count'], 1)
        self.assertEqual(results['first'], self.invoice2)

    def test_superuser_sees_everything(self):
        """Verify that superusers can still see everything by default."""
        admin_user = User.objects.create_superuser(username="admin", email="admin@example.com", password="password")
        request = self.factory.get("/")
        request.user = admin_user
        
        middleware = TenantMiddleware(get_response=lambda r: None)
        middleware(request)
        
        all_invoices = Invoice.objects.all()
        self.assertEqual(all_invoices.count(), 2)

    def test_no_user_sees_nothing_or_everything(self):
        """
        Verify behavior when no user is logged in. 
        Usually it should see nothing or everything depending on design.
        In our current implementation, if no user is set, it returns all (unfiltered).
        """
        request = self.factory.get("/")
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        
        middleware = TenantMiddleware(get_response=lambda r: None)
        middleware(request)
        
        all_invoices = Invoice.objects.all()
        self.assertEqual(all_invoices.count(), 2)
