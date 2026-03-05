# timesheets/forms.py
from django import forms

from .models import TimesheetEntry, WorkCategory


class TimesheetEntryForm(forms.ModelForm):
    class Meta:
        model = TimesheetEntry
        fields = ["client", "date", "hours", "hourly_rate", "category", "todo"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
            "hourly_rate": forms.NumberInput(attrs={"class": "form-control"}),
            "client": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "todo": forms.HiddenInput(),
        }
        help_texts = {
            'category': '',  # Remove default help text
        }

    def __init__(self, *args, **kwargs):
        # Extract user before calling parent __init__
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        print(f"[DEBUG FORM] Initializing TimesheetEntryForm")
        print(f"[DEBUG FORM] User: {user}")
        print(f"[DEBUG FORM] Initial data: {self.initial}")
        
        # Filter categories by current user if available
        if user:
            cats = WorkCategory.objects.filter(user=user)
            self.fields['category'].queryset = cats
            print(f"[DEBUG FORM] Set category queryset for user {user.username}: {list(cats.values_list('id', 'name'))}")
            if 'category' in self.initial:
                print(f"[DEBUG FORM] Category in initial: {self.initial['category']}")
        else:
            # Try to get from instance
            if self.instance and self.instance.pk:
                cats = WorkCategory.objects.filter(user=self.instance.user)
                self.fields['category'].queryset = cats
                print(f"[DEBUG FORM] Set category queryset from instance user: {list(cats.values_list('id', 'name'))}")
        
        # Disable client field if timesheet is already linked to an invoice
        if self.instance and self.instance.pk and self.instance.invoice_id:
            self.fields["client"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        
        # Prevent changing client if timesheet is already in an invoice (business rule from TimesheetManager)
        if self.instance and self.instance.pk and self.instance.invoice_id:
            if cleaned_data.get("client") != self.instance.client:
                raise forms.ValidationError(
                    "Cannot change the client for timesheets that are already linked to an invoice. "
                    "The timesheet must stay with its original client."
                )
        
        return cleaned_data


class WorkCategoryForm(forms.ModelForm):
    # This helps users enter comma-separated values for fields
    metadata_schema_raw = forms.CharField(
        label="Fields (comma separated)",
        help_text="e.g. Project_Phase, Stakeholder, Location",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Field1, Field2"}),
    )

    class Meta:
        model = WorkCategory
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill metadata_schema_raw with existing data when editing
        if self.instance and self.instance.pk:
            if self.instance.metadata_schema:
                self.fields['metadata_schema_raw'].initial = ", ".join(self.instance.metadata_schema)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Convert the raw string into a list for the JSON metadata_schema
        raw_data = self.cleaned_data.get("metadata_schema_raw", "")
        instance.metadata_schema = [item.strip() for item in raw_data.split(",") if item.strip()]
        if commit:
            instance.save()
        return instance
