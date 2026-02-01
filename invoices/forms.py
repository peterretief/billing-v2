from django import forms
from django.utils import timezone

from .models import Invoice, TaxPayment


class VATPaymentForm(forms.ModelForm):
    class Meta:
        model = TaxPayment
        fields = ['payment_date', 'amount', 'reference', 'tax_type']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. VAT201 Jan 2026'}),
            'tax_type': forms.HiddenInput(),
        }

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



