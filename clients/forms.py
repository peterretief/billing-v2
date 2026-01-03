from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit
from .models import Client

class ClientForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('name', css_class='col-md-8'),
                Column('client_code', css_class='col-md-4'),
            ),
            Row(
                Column('email', css_class='col-md-6'),
                Column('phone', css_class='col-md-6'),
            ),
            'address',
            Row(
                Column('vat_number', css_class='col-md-4'),
                Column('tax_number', css_class='col-md-4'),
                Column('vendor_number', css_class='col-md-4'),
            ),
            Submit('submit', 'Save Client', css_class='btn-primary mt-3')
        )

    class Meta:
        model = Client
        fields = '__all__'
        exclude = ['user', 'client_code'] # client_code is auto-generated in model.save()


