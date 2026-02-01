# timesheets/forms.py
from django import forms

from .models import TimesheetEntry, WorkCategory


class TimesheetEntryForm(forms.ModelForm):
    class Meta:
        model = TimesheetEntry
        fields = ['client', 'date', 'description', 'hours', 'hourly_rate']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'What did you do?'}),
            'hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'client': forms.Select(attrs={'class': 'form-select'}),
        }


class WorkCategoryForm(forms.ModelForm):
    # This helps users enter comma-separated values for fields
    metadata_schema_raw = forms.CharField(
        label="Fields (comma separated)",
        help_text="e.g. Project_Phase, Stakeholder, Location",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Field1, Field2'})
    )

    class Meta:
        model = WorkCategory
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Convert the raw string into a list for the JSON metadata_schema
        raw_data = self.cleaned_data.get('metadata_schema_raw', '')
        instance.metadata_schema = [item.strip() for item in raw_data.split(',') if item.strip()]
        if commit:
            instance.save()
        return instance        