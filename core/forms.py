from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.humanize.templatetags.humanize import intcomma

from .models import GroupMember, User, UserProfile


class WorkingHoursForm(forms.ModelForm):
    """Form for configuring working hours and scheduling preferences."""
    
    # Day selection checkboxes
    monday = forms.BooleanField(required=False, label="Monday")
    tuesday = forms.BooleanField(required=False, label="Tuesday")
    wednesday = forms.BooleanField(required=False, label="Wednesday")
    thursday = forms.BooleanField(required=False, label="Thursday")
    friday = forms.BooleanField(required=False, label="Friday")
    saturday = forms.BooleanField(required=False, label="Saturday")
    sunday = forms.BooleanField(required=False, label="Sunday")
    
    class Meta:
        model = UserProfile
        fields = ["work_start_time", "work_end_time", "break_minutes"]
        widgets = {
            "work_start_time": forms.TimeInput(attrs={
                "type": "time",
                "class": "form-control",
                "help_text": "e.g., 09:00"
            }),
            "work_end_time": forms.TimeInput(attrs={
                "type": "time",
                "class": "form-control",
                "help_text": "e.g., 17:00"
            }),
            "break_minutes": forms.NumberInput(attrs={
                "class": "form-control",
                "type": "number",
                "min": "0",
                "max": "120",
                "step": "5",
                "help_text": "Buffer time between appointments (minutes)"
            }),
        }
        labels = {
            "work_start_time": "Start Time",
            "work_end_time": "End Time",
            "break_minutes": "Break Between Appointments (minutes)",
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate day checkboxes from work_days
        if self.instance and self.instance.pk:
            work_days = self.instance.get_work_days()
            day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            for i, day_name in enumerate(day_names):
                self.fields[day_name].initial = i in work_days
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Get selected work days
        work_days = []
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for i, day_name in enumerate(day_names):
            if cleaned_data.get(day_name):
                work_days.append(i)
        
        if not work_days:
            raise forms.ValidationError("You must select at least one work day.")
        
        cleaned_data["work_days"] = work_days
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.work_days = self.cleaned_data.get("work_days", [0, 1, 2, 3, 4])
        if commit:
            instance.save()
        return instance



class AppInterestForm(forms.Form):
    name = forms.CharField(
        max_length=100, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Your Name"})
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "your@email.com"}))
    understanding = forms.CharField(
        label="Do you understand what this app does?",
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 3, "placeholder": "Tell me your take on the app..."}
        ),
    )


class AdminUserCreationForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            "company_name",
            "contact_name",
            "business_email",
            "monthly_target",
            "currency",
            "invoice_footer",
            "is_vat_registered",
            "vat_rate",
            "phone",
            "logo",
            "vat_number",
            "tax_number",
            "vendor_number",
            "address",
            "bank_name",
            "account_holder",
            "account_number",
            "branch_code",
            "swift_bic",
        ]
        labels = {
            "vat_rate": "Default VAT Rate (%)",
            "company_name": "Business Name",
            "is_vat_registered": "VAT Registered User",
            "monthly_target": "Monthly Revenue Target (R)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check if this profile has already completed initial setup
        if self.instance and self.instance.initial_setup_complete:
            self.fields["currency"].disabled = True
            self.fields["is_vat_registered"].disabled = True

            # Add a help text to explain why
            self.fields["currency"].help_text = "Locked for accounting integrity."
            self.fields["is_vat_registered"].help_text = "Consult an expert before changing VAT status."

        # 1. Automatic Bootstrap Styling for ALL fields
        for name, field in self.fields.items():
            css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.update({"class": css_class})

        # 2. Add the Revenue Forecast Logic
        if self.instance and self.instance.pk:
            # Note: Ensure annual_revenue_forecast is defined in your UserProfile model
            forecast = self.instance.annual_revenue_forecast
            self.fields[
                "monthly_target"
            ].help_text = f"Your current annual forecast is {self.instance.currency} {intcomma(forecast)}**."


class UserGroupForm(forms.Form):
    """Form for adding a test user to the staff user's group."""

    add_user_email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "User email"}), label="User Email"
    )
    add_user_username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Username"}),
        label="Username",
    )

    def clean_add_user_email(self):
        """Check if email already exists."""
        email = self.cleaned_data["add_user_email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(f"A user with email {email} already exists.")
        return email

    def clean_add_user_username(self):
        """Check if username already exists."""
        username = self.cleaned_data["add_user_username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(f"Username {username} is already taken.")
        return username


class AddGroupMemberForm(forms.ModelForm):
    """Form for adding members to a group."""

    class Meta:
        model = GroupMember
        fields = ["user", "role"]
        widgets = {
            "user": forms.Select(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, group=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        self.user = user

        # Restrict user choices based on permissions
        if group:
            existing_members = GroupMember.objects.filter(group=group).values_list("user_id", flat=True)

            if user and not user.is_superuser:
                # Managers can only add bound tenant users (non-staff)
                queryset = User.objects.filter(is_staff=False, is_superuser=False).exclude(id__in=existing_members)
            else:
                # Superuser can add any non-superuser
                queryset = User.objects.filter(is_superuser=False).exclude(id__in=existing_members)

            self.fields["user"].queryset = queryset

            if not queryset.exists():
                # Add a helpful message if no users available
                self.fields["user"].help_text = "No available users to add. Create new tenant users first."

    def clean(self):
        """Validate that user is not already in group."""
        cleaned_data = super().clean()
        user = cleaned_data.get("user")

        if user and self.group:
            if GroupMember.objects.filter(group=self.group, user=user).exists():
                raise forms.ValidationError("This user is already a member of this group.")

        return cleaned_data


class StaffCreateAndAddUserForm(forms.Form):
    """Form for staff to create a new user and add to group in one step."""

    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}), label="Email Address")
    username = forms.CharField(
        max_length=150, widget=forms.TextInput(attrs={"class": "form-control"}), label="Username"
    )

    def clean_email(self):
        """Check if email already exists."""
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_username(self):
        """Check if username already exists."""
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username


class BulkAddGroupMembersForm(forms.Form):
    """Form for bulk adding users to a group via email addresses."""

    emails = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "One email per line"}),
        help_text="Enter email addresses of users to add to this group (one per line)",
        label="User Emails",
    )

    role = forms.ChoiceField(
        choices=GroupMember._meta.get_field("role").choices,
        widget=forms.Select(attrs={"class": "form-control"}),
        initial="TENANT",
    )

    def clean_emails(self):
        """Validate and parse email list."""
        emails_text = self.cleaned_data.get("emails", "")
        emails = [e.strip().lower() for e in emails_text.split("\n") if e.strip()]

        if not emails:
            raise forms.ValidationError("Please provide at least one email address.")

        return emails

class AuditSettingsForm(forms.ModelForm):
    """Form for configuring invoice audit and anomaly detection settings."""

    class Meta:
        model = UserProfile
        fields = [
            "audit_enabled",
            "audit_sensitivity",
        ]
        labels = {
            "audit_enabled": "Enable Anomaly Detection",
            "audit_sensitivity": "Detection Sensitivity",
        }
        help_texts = {
            "audit_enabled": "When disabled, all invoices are processed without anomaly checks.",
            "audit_sensitivity": "Choose how strict the system should be about flagging unusual invoice amounts.",
        }

    # Audit trigger checkboxes
    detect_math_error = forms.BooleanField(required=False, label="🔍 Detect math errors (total ≠ sum of items) - CATCHES CORRUPTION")
    detect_zero_total = forms.BooleanField(required=False, label="Flag invoices with $0 total")
    detect_no_items = forms.BooleanField(required=False, label="Flag invoices with no line items")
    detect_statistical_outliers = forms.BooleanField(required=False, label="Flag statistical outliers (info only)")
    detect_email_delivery_failure = forms.BooleanField(required=False, label="Flag email delivery failures (bounce, deferred, etc.)")
    detect_missing_email = forms.BooleanField(required=False, label="Flag missing client email")
    detect_vat_mismatch = forms.BooleanField(required=False, label="Flag VAT inconsistencies")
    detect_duplicate_items = forms.BooleanField(required=False, label="Flag duplicate line items")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Style the form controls
        self.fields["audit_enabled"].widget.attrs.update({"class": "form-check-input"})
        self.fields["audit_sensitivity"].widget.attrs.update({"class": "form-select"})

        # Initialize trigger checkboxes from audit_triggers
        if self.instance and self.instance.pk:
            triggers = self.instance.get_audit_triggers()
            self.fields["detect_math_error"].initial = triggers.get("detect_math_error", True)
            self.fields["detect_zero_total"].initial = triggers.get("detect_zero_total", True)
            self.fields["detect_no_items"].initial = triggers.get("detect_no_items", True)
            self.fields["detect_statistical_outliers"].initial = triggers.get("detect_statistical_outliers", False)
            self.fields["detect_email_delivery_failure"].initial = triggers.get("detect_email_delivery_failure", False)
            self.fields["detect_missing_email"].initial = triggers.get("detect_missing_email", False)
            self.fields["detect_vat_mismatch"].initial = triggers.get("detect_vat_mismatch", False)
            self.fields["detect_duplicate_items"].initial = triggers.get("detect_duplicate_items", True)

        # Style all trigger checkboxes
        for field in [
            "detect_math_error",
            "detect_zero_total",
            "detect_no_items",
            "detect_statistical_outliers",
            "detect_email_delivery_failure",
            "detect_missing_email",
            "detect_vat_mismatch",
            "detect_duplicate_items",
        ]:
            self.fields[field].widget.attrs.update({"class": "form-check-input"})

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Save trigger configuration to JSON
        instance.audit_triggers = {
            "detect_math_error": self.cleaned_data.get("detect_math_error", True),
            "detect_zero_total": self.cleaned_data.get("detect_zero_total", True),
            "detect_no_items": self.cleaned_data.get("detect_no_items", True),
            "detect_statistical_outliers": self.cleaned_data.get("detect_statistical_outliers", False),
            "detect_email_delivery_failure": self.cleaned_data.get("detect_email_delivery_failure", False),
            "detect_missing_email": self.cleaned_data.get("detect_missing_email", False),
            "detect_vat_mismatch": self.cleaned_data.get("detect_vat_mismatch", False),
            "detect_duplicate_items": self.cleaned_data.get("detect_duplicate_items", True),
        }

        if commit:
            instance.save()
        return instance