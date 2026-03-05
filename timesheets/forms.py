# timesheets/forms.py
from django import forms

from .models import TimesheetEntry, WorkCategory


class TimesheetEntryForm(forms.ModelForm):
    class Meta:
        model = TimesheetEntry
        fields = ["client", "date", "hours", "hourly_rate", "todo"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
            "hourly_rate": forms.NumberInput(attrs={"class": "form-control"}),
            "client": forms.Select(attrs={"class": "form-select"}),
            "todo": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
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
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Field1, Field2"}),
    )

    class Meta:
        model = WorkCategory
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Convert the raw string into a list for the JSON metadata_schema
        raw_data = self.cleaned_data.get("metadata_schema_raw", "")
        instance.metadata_schema = [item.strip() for item in raw_data.split(",") if item.strip()]
        if commit:
            instance.save()
        return instance
