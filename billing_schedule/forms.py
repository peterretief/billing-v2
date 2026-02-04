from django import forms

from .models import BillingPolicy


class BillingPolicyForm(forms.ModelForm):
    class Meta:
        model = BillingPolicy
        fields = ['name', 'run_day', 'special_rule', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., Standard Monthly Subscription'
            }),
            'run_day': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': '1', 
                'max': '31',
                'placeholder': '1-31'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'run_day': 'Day of the Month to Run',
            'is_active': 'Enable Automatic Invoicing'
        }


    def clean(self):
        cleaned_data = super().clean()
        run_day = cleaned_data.get('run_day')
        special_rule = cleaned_data.get('special_rule')

        if special_rule == 'NONE' and not run_day:
            raise forms.ValidationError(
                "Please either specify a Day of the Month or select a Special Rule."
            )
    
        if special_rule != 'NONE' and run_day:
            # If they pick both, we clear the run_day to prioritize the rule
            cleaned_data['run_day'] = None
        
        return cleaned_data

    def clean_run_day(self):
        day = self.cleaned_data.get('run_day')
        special_rule = self.data.get('special_rule') # Look at the raw POST data

        # If a special rule is selected, we don't care if run_day is empty
        if special_rule and special_rule != 'NONE':
            return None

        # If NO special rule is selected, THEN we enforce the 1-31 rule
        if day is None:
            raise forms.ValidationError("Please specify a day of the month.")
        
        if day < 1 or day > 31:
            raise forms.ValidationError("Please select a day between 1 and 31.")
        
        return day