from django import forms
from .models import UserProfile



class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'company_name', 
            'business_email', # The second optional email
            'is_vat_registered',
            'phone', 
            'logo', 
            'vat_number', 
            'tax_number',
            'vendor_number',
            'address', 
            'tax_rate',
            'bank_name',
            'account_holder',
            'account_number',
            'branch_code',
        ]
        widgets = {
            # Standard Bootstrap classes for all fields
            'business_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'billing@yourcompany.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),

            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Acme Corp'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'vat_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'bank_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Bank, Acc No, Branch Code...'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        }
        labels = {
            'tax_rate': 'Default VAT Rate (%)',
            'company_name': 'Business Name',
        }

    def clean_tax_rate(self):
        """Ensure the tax rate is a positive number."""
        tax_rate = self.cleaned_data.get('tax_rate')
        if tax_rate < 0:
            raise forms.ValidationError("Tax rate cannot be negative.")
        return tax_rate