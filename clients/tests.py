from clients.models import Client
from core.tests import BaseBillingTest


class ClientUniquenessTest(BaseBillingTest):
    
    def test_duplicate_code_rejected(self):
        from django.db import IntegrityError
        # self.client_obj already exists with code "CL-..."
        with self.assertRaises(IntegrityError):
            Client.objects.create(
                user=self.user, 
                name="Duplicate", 
                client_code=self.client_obj.client_code
            )