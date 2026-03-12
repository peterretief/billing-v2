
from clients.forms import ClientForm
from clients.models import Client
from core.tests import BaseBillingTest


class ClientUniquenessTest(BaseBillingTest):
    def test_duplicate_code_rejected(self):
        from django.db import IntegrityError

        # self.client_obj already exists with code "CL-..."
        with self.assertRaises(IntegrityError):
            Client.objects.create(user=self.user, name="Duplicate", client_code=self.client_obj.client_code)


class ClientFormUniquenessTest(BaseBillingTest):
    """Test form-level validation for client code uniqueness."""

    def _get_form_data(self, **overrides):
        """Helper to get valid form data with required fields."""
        data = {
            "name": "Test Client",
            "client_code": "TEST",
            "email": "test@example.com",
            "phone": "555-1234",
            "payment_terms": 14,
            "default_hourly_rate": "100.00",
            "weekly_target_hours": "0.00",
            "monthly_target_hours": "0.00",
        }
        data.update(overrides)
        return data

    def test_create_client_with_unique_code(self):
        """Creating a new client with a unique code should succeed."""
        form = ClientForm(
            data=self._get_form_data(
                name="New Client",
                client_code="NEWC",
            ),
            instance=Client(user=self.user),
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_create_client_with_duplicate_code_fails(self):
        """Creating a new client with existing code should fail validation."""
        # self.client_obj already exists with code "CL-xxx"
        existing_code = self.client_obj.client_code

        form = ClientForm(
            data=self._get_form_data(
                name="Another Client",
                client_code=existing_code,
            ),
            instance=Client(user=self.user),
        )
        self.assertFalse(form.is_valid(), "Form should reject duplicate code")
        self.assertIn("client_code", form.errors)
        self.assertIn("already in use", str(form.errors["client_code"][0]))

    def test_edit_client_without_changing_code(self):
        """Editing a client without changing its code should succeed."""
        form = ClientForm(
            data=self._get_form_data(
                name="Updated Name",
                client_code=self.client_obj.client_code,  # Same code as before
            ),
            instance=self.client_obj,
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_edit_client_with_unique_new_code(self):
        """Editing a client to change to a new unique code should succeed."""
        form = ClientForm(
            data=self._get_form_data(
                name=self.client_obj.name,
                client_code="NEWCODE",  # Different code
                email=self.client_obj.email or "test@example.com",
                phone=self.client_obj.phone or "555-5555",
            ),
            instance=self.client_obj,
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_edit_client_with_duplicate_code_fails(self):
        """Editing a client to use an existing code should fail."""
        # Create a second client
        client2 = Client.objects.create(user=self.user, name="Client 2", client_code="CLI2")

        # Try to edit client2 to use client1's code
        form = ClientForm(
            data=self._get_form_data(
                name=client2.name,
                client_code=self.client_obj.client_code,  # Use first client's code
                email=client2.email,
                phone=client2.phone,
            ),
            instance=client2,
        )
        self.assertFalse(form.is_valid(), "Form should reject duplicate code during edit")
        self.assertIn("client_code", form.errors)

    def test_create_client_with_blank_code_autogenerates(self):
        """Creating a client with blank code should allow auto-generation."""
        form = ClientForm(
            data=self._get_form_data(
                name="Auto Code Client",
                client_code="",  # Blank - should be auto-generated
            ),
            instance=Client(user=self.user),
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        # Form should be valid; model's save() will generate the code

    def test_edit_client_with_blank_code_preserves_existing(self):
        """Editing a client with blank code should preserve the existing code."""
        original_code = self.client_obj.client_code

        form = ClientForm(
            data=self._get_form_data(
                name="Modified Name",
                client_code="",  # Blank
                email=self.client_obj.email or "preserve@example.com",
                phone=self.client_obj.phone or "555-3333",
            ),
            instance=self.client_obj,
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        # The blank code should pass validation (it will be handled in model save)

    def test_different_user_can_use_same_code(self):
        """A different user should be able to use the same client code."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        other_user = User.objects.create_user(username="otheruser", password="pass")

        # Create a client for the other user with the same code as self.client_obj
        form = ClientForm(
            data=self._get_form_data(
                name="Other User's Client",
                client_code=self.client_obj.client_code,
                email="other@example.com",
            ),
            instance=Client(user=other_user),
        )
        self.assertTrue(form.is_valid(), "Different users should be able to use the same code")
