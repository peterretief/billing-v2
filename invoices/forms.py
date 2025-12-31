from django import forms
from django.forms import inlineformset_factory
from .models import Invoice, InvoiceItem

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        # Includes tax_exempt so you can toggle VAT for the whole invoice
        fields = ['client', 'number', 'date_issued', 'due_date', 'status', 'tax_exempt']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'INV-001'}),
            'date_issued': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'tax_exempt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class InvoiceItemForm(forms.ModelForm):
    # This adds the dropdown for your services
    preset_description = forms.ChoiceField(
        choices=[('', '--- Select a Service ---')] + InvoiceItem.PRESET_DESCRIPTIONS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control preset-select'})
    )

    class Meta:
        model = InvoiceItem
        # Combined fields from both your versions
        fields = ['preset_description', 'description', 'quantity', 'unit_price', 'is_taxable']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_taxable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set a default unit price for new rows
        if not self.instance.pk:
            self.fields['unit_price'].initial = 750.00

# The Factory connects the Invoice and its Items
InvoiceItemFormSet = inlineformset_factory(
    Invoice, 
    InvoiceItem,
    form=InvoiceItemForm,
    extra=1,           # Number of empty rows to start with
    can_delete=True    # Allows removing rows
)