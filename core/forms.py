from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.humanize.templatetags.humanize import intcomma

from .models import User, UserProfile


class AppInterestForm(forms.Form):
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Your Name'
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'form-control', 'placeholder': 'your@email.com'
    }))
    understanding = forms.CharField(
        label="Do you understand what this app does?",
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3, 
            'placeholder': 'Tell me your take on the app...'
        })
    )

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
            'swift_bic',
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
            css_class = 'form-check-input' if \
                isinstance(field.widget, forms.CheckboxInput) else 'form-control'
            field.widget.attrs.update({'class': css_class})
            
        # 2. Add the Revenue Forecast Logic
        if self.instance and self.instance.pk:
            # Note: Ensure annual_revenue_forecast is defined in your UserProfile model
            forecast = self.instance.annual_revenue_forecast
            self.fields['monthly_target'].help_text = (
                f"Your current annual forecast is **R {intcomma(forecast)}**."
            )