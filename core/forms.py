from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.humanize.templatetags.humanize import intcomma

from .models import GroupMember, User, UserProfile


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
            'contact_name',
            'business_email',
            'monthly_target',
            'currency',
            'invoice_footer',
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
        
        # Check if this profile has already completed initial setup
        if self.instance and self.instance.initial_setup_complete:
            self.fields['currency'].disabled = True
            self.fields['is_vat_registered'].disabled = True
            
            # Add a help text to explain why
            self.fields['currency'].help_text = "Locked for accounting integrity."
            self.fields['is_vat_registered'].help_text = "Consult an expert before changing VAT status."

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
                f"Your current annual forecast is {self.instance.currency} {intcomma(forecast)}**."
            )


class UserGroupForm(forms.Form):
    """Form for adding a test user to the staff user's group."""
    
    add_user_email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'User email'}),
        label='User Email'
    )
    add_user_username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
        label='Username'
    )
    
    def clean_add_user_email(self):
        """Check if email already exists."""
        email = self.cleaned_data['add_user_email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(f'A user with email {email} already exists.')
        return email
    
    def clean_add_user_username(self):
        """Check if username already exists."""
        username = self.cleaned_data['add_user_username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(f'Username {username} is already taken.')
        return username


class AddGroupMemberForm(forms.ModelForm):
    """Form for adding members to a group."""
    
    class Meta:
        model = GroupMember
        fields = ['user', 'role']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, group=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        self.user = user
        
        # Restrict user choices based on permissions
        if group:
            existing_members = GroupMember.objects.filter(
                group=group
            ).values_list('user_id', flat=True)
            
            if user and not user.is_superuser:
                # Managers can only add bound tenant users (non-staff)
                queryset = User.objects.filter(
                    is_staff=False,
                    is_superuser=False
                ).exclude(id__in=existing_members)
            else:
                # Superuser can add any non-superuser
                queryset = User.objects.filter(
                    is_superuser=False
                ).exclude(id__in=existing_members)
            
            self.fields['user'].queryset = queryset
            
            if not queryset.exists():
                # Add a helpful message if no users available
                self.fields['user'].help_text = 'No available users to add. Create new tenant users first.'
    
    def clean(self):
        """Validate that user is not already in group."""
        cleaned_data = super().clean()
        user = cleaned_data.get('user')
        
        if user and self.group:
            if GroupMember.objects.filter(group=self.group, user=user).exists():
                raise forms.ValidationError('This user is already a member of this group.')
        
        return cleaned_data


class StaffCreateAndAddUserForm(forms.Form):
    """Form for staff to create a new user and add to group in one step."""
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        label='Email Address'
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Username'
    )
    
    def clean_email(self):
        """Check if email already exists."""
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email
    
    def clean_username(self):
        """Check if username already exists."""
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username


class BulkAddGroupMembersForm(forms.Form):
    """Form for bulk adding users to a group via email addresses."""
    
    emails = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'One email per line'
        }),
        help_text='Enter email addresses of users to add to this group (one per line)',
        label='User Emails'
    )
    
    role = forms.ChoiceField(
        choices=GroupMember._meta.get_field('role').choices,
        widget=forms.Select(attrs={'class': 'form-control'}),
        initial='TENANT'
    )

    def clean_emails(self):
        """Validate and parse email list."""
        emails_text = self.cleaned_data.get('emails', '')
        emails = [e.strip().lower() for e in emails_text.split('\n') if e.strip()]
        
        if not emails:
            raise forms.ValidationError('Please provide at least one email address.')
        
        return emails