from django import forms
from django.forms import inlineformset_factory
from .models import Invoice, InvoiceItem

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        # Make sure 'billing_type' is in your model fields if you want to toggle it!
        fields = ['client', 'date_issued', 'due_date', 'status']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-control'}),
            'date_issued': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

class InvoiceItemForm(forms.ModelForm):
    preset_description = forms.ChoiceField(
        choices=[('', '--- Select a Service ---')] + InvoiceItem.PRESET_DESCRIPTIONS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = InvoiceItem
        fields = ['preset_description', 'description', 'quantity', 'unit_price']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['unit_price'].initial = 750.00

# IMPORTANT: Added 'form=InvoiceItemForm' so the dropdown shows up in the set
InvoiceItemFormSet = inlineformset_factory(
    Invoice, 
    InvoiceItem,
    form=InvoiceItemForm,
    fields=['preset_description', 'description', 'quantity', 'unit_price'],
    extra=1,
    can_delete=True
)

