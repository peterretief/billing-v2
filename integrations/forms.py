from django import forms
from .models import IntegrationSettings

class IntegrationSettingsForm(forms.ModelForm):
    class Meta:
        model = IntegrationSettings
        fields = ['items_enabled', 'inventory_enabled', 'timesheets_enabled', 'calendar_events_enabled', 'barcodes_enabled'] # 'recipes_enabled'
        widgets = {
            'items_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'inventory_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'timesheets_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'calendar_events_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'barcodes_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            # 'recipes_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }
