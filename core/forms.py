from django import forms
from .models import UserProfile, User
from decimal import Decimal
from django.contrib.auth.forms import UserCreationForm
from django.contrib.humanize.templatetags.humanize import intcomma


class AdminUserCreationForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'company_name', 
            'business_email',
            'monthly_target',  # <-- IMPORTANT: Added this back in
            'is_vat_registered',
            'vat_rate', 
            'phone', 
            'logo', 
            'vat_number', 
            'tax_number',
            'vendor_number',
            'address', 
            'bank_name',
            'account_holder',
            'account_number',
            'branch_code',
        ]
        labels = {
            'vat_rate': 'Default VAT Rate (%)',
            'company_name': 'Business Name',
            'is_vat_registered': 'VAT Registered User',
            'monthly_target': 'Monthly Revenue Target (R)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 1. Automatic Bootstrap Styling for ALL fields
        for name, field in self.fields.items():
            css_class = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-control'
            field.widget.attrs.update({'class': css_class})
            
        # 2. Add the Revenue Forecast Logic
        if self.instance and self.instance.pk:
            # Note: Ensure annual_revenue_forecast is defined in your UserProfile model
            forecast = self.instance.annual_revenue_forecast
            self.fields['monthly_target'].help_text = (
                f"Your current annual forecast is **R {intcomma(forecast)}**."
            )