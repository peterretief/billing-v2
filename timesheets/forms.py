# timesheets/forms.py
from django import forms
from .models import TimesheetEntry

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