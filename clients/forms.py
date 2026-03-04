from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Submit
from django import forms
from django.core.exceptions import ValidationError

from .models import Client


class ClientForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.initial.get("client"):
            client = self.initial.get("client")
            self.fields["hourly_rate"].initial = client.default_hourly_rate

        # Add help text for client_code
        if "client_code" in self.fields:
            self.fields["client_code"].help_text = "Auto-generated from client name, but you can customize it (max 10 characters, unique per client)"
            self.fields["client_code"].required = False

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column("name", css_class="col-md-8"),
                Column("client_code", css_class="col-md-4"),
            ),
            Row(
                Column("email", css_class="col-md-6"),
                Column("phone", css_class="col-md-6"),
            ),
            "address",
            Row(
                Column("vat_number", css_class="col-md-4"),
                Column("tax_number", css_class="col-md-4"),
                Column("vendor_number", css_class="col-md-4"),
            ),
            Submit("submit", "Save Client", css_class="btn-primary mt-3"),
        )

    def clean_email(self):
        """Validate email - warn about test/fake emails."""
        email = self.cleaned_data.get("email", "").strip().lower()
        
        # Warn about obvious test/fake emails
        test_patterns = [
            "test@", "@test.", "fake@", "cancel@", "nope@", "no-reply@",
            "dev@", "demo@", "example@", "sample@", "temp@", "dummy@"
        ]
        
        for pattern in test_patterns:
            if pattern in email:
                raise ValidationError(
                    f"⚠️ This looks like a test email: '{email}'. "
                    f"Invoices sent to test addresses will bounce. Is this correct?"
                )
        
        return email

    def clean_client_code(self):
        """Validate that client_code is unique per user."""
        client_code = self.cleaned_data.get("client_code")
        
        if not client_code:
            # If empty, it will be auto-generated in the model save()
            return client_code
        
        # Check for uniqueness (excluding the current instance if editing)
        qs = Client.objects.filter(user=self.instance.user, client_code=client_code)
        
        if self.instance.pk:
            # Editing: exclude the current client
            qs = qs.exclude(pk=self.instance.pk)
        
        if qs.exists():
            raise ValidationError(
                f"This client code '{client_code}' is already in use. Please choose a different code."
            )
        
        return client_code

    class Meta:
        model = Client
        fields = "__all__"
        exclude = ["user"]  # user is set by the view
