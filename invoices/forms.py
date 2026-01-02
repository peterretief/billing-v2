from django import forms
from django.forms import inlineformset_factory
from .models import Invoice, InvoiceItem
from django.utils import timezone


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['client', 'number', 'billing_type', 'date_issued', 'due_date', 'status', 'tax_mode']
        widgets = {
            'date_issued': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'client': forms.Select(attrs={'class': 'form-select'}),
            'number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto-generated if blank'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'tax_mode': forms.Select(attrs={'class': 'form-select'}),
            'billing_type': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            today = timezone.now().date()
            self.fields['date_issued'].initial = today
            self.fields['due_date'].initial = today
        self.fields['number'].required = False # Allow signal to handle it



class InvoiceItemForm(forms.ModelForm):
    # 1. Define the extra field
    preset_description = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select preset-select'})
    )

    class Meta:
        model = InvoiceItem
        fields = ['preset_description', 'description', 'quantity', 'unit_price', 'is_taxable']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 2. Assign choices dynamically to avoid boot-up errors
        self.fields['preset_description'].choices = [('', '--- Select a Service ---')] + InvoiceItem.Preset.choices

        


# The Factory connects the Invoice and its Items
InvoiceItemFormSet = inlineformset_factory(
    Invoice, 
    InvoiceItem,
    form=InvoiceItemForm,
    extra=1,           # Number of empty rows to start with
    can_delete=True    # Allows removing rows
)