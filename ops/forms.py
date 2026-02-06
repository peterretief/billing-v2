from crispy_forms.helper import FormHelper
from crispy_forms.layout import Button, Fieldset, Layout, Submit
from django import forms


class TenantInviteForm(forms.Form):
    # User Details
    username = forms.CharField(max_length=150)
    email = forms.EmailField()

    # Profile / Oversight Details
    company_name = forms.CharField(max_length=255)
    currency = forms.ChoiceField(choices=[('R', 'Rand'), ('GBP', 'GBP'), ('EUR', 'EUR'), ('USD', 'USD')])
    vat_number = forms.CharField(required=False, label="VAT Number")
    vat_rate = forms.DecimalField(initial=15.00, label="VAT Rate (%)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'User Details',
                'username',
                'email',
            ),
            Fieldset(
                'Company & Tax Information',
                'company_name',
                'currency',
                'vat_number',
                'vat_rate',
            ),
            Submit('submit', 'Send Invitation', css_class='btn-success mt-3'),
            Button('cancel', 'Cancel', css_class='btn-secondary mt-3', onclick="window.history.back()")
        )