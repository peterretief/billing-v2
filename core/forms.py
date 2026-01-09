from django import forms
from .models import UserProfile
from decimal import Decimal

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'company_name', 
            'business_email',
            'is_vat_registered',
            'phone', 
            'logo', 
            'vat_number', 
            'tax_number',
            'vendor_number',
            'address', 
            'vat_rate', # Changed from tax_rate to match model
            'bank_name',
            'account_holder',
            'account_number',
            'branch_code',
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Acme Corp'}),
            'business_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'billing@yourcompany.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'vat_number': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'vendor_number': forms.TextInput(attrs={'class': 'form-control'}),
            'vat_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_holder': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'branch_code': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'vat_rate': 'Default VAT Rate (%)',
            'company_name': 'Business Name',
            'is_vat_registered': 'VAT Registered User',
        }

    def clean_vat_rate(self):
        """Ensure the VAT rate is a positive number."""
        rate = self.cleaned_data.get('vat_rate')
        if rate is not None and rate < 0:
            raise forms.ValidationError("VAT rate cannot be negative.")
        return rate