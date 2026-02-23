from django import forms
from django.utils import timezone
from decimal import Decimal

from .models import Invoice, TaxPayment, CreditNote
from clients.models import Client


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




class CreditNoteForm(forms.ModelForm):
    """User-friendly form for creating credit notes with validation."""
    
    class Meta:
        model = CreditNote
        fields = ['client', 'invoice', 'note_type', 'amount', 'reference', 'description', 'issued_date']
        widgets = {
            'client': forms.Select(attrs={
                'class': 'form-select',
                'required': 'required'
            }),
            'invoice': forms.Select(attrs={
                'class': 'form-select',
                'help_text': 'Optional - link to specific invoice if available'
            }),
            'note_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
                'required': 'required'
            }),
            'reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., CN2026-001 (auto-generated if left blank)',
                'maxlength': '100'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Reason for credit note (e.g., Overpayment adjustment, Discount applied)',
                'required': 'required'
            }),
            'issued_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'required': 'required'
            }),
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default issued_date to today
        if not self.instance.pk:
            self.fields['issued_date'].initial = timezone.now().date()
        
        # Filter clients to current user only
        if user:
            self.fields['client'].queryset = Client.objects.filter(user=user).order_by('name')
            self.fields['invoice'].queryset = Invoice.objects.filter(
                user=user
            ).select_related('client').order_by('-date_issued')
        
        # Make invoice optional
        self.fields['invoice'].required = False
        self.fields['reference'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        client = cleaned_data.get('client')
        description = cleaned_data.get('description')
        
        # Validate minimum amount
        if amount and amount <= Decimal('0.00'):
            self.add_error('amount', 'Credit note amount must be greater than £0.00')
        
        # Validate client is selected
        if not client:
            self.add_error('client', 'Please select a client')
        
        # Validate description for certain note types
        note_type = cleaned_data.get('note_type')
        if note_type in ['ADJUSTMENT', 'CANCELLATION'] and not description:
            self.add_error('description', f'{note_type} requires a description for audit trail')
        
        return cleaned_data
