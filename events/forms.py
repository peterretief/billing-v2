from django import forms

from timesheets.models import WorkCategory

from .models import Event


class EventForm(forms.ModelForm):
    # Custom field for "Select or add new" category
    category_text = forms.CharField(
        label="Work Category",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Select existing or type new category name...',
            'list': 'category_list',
        }),
        help_text="Select from dropdown or type a new category name"
    )
    
    class Meta:
        model = Event
        fields = ['category', 'description', 'client', 'status', 'priority', 'due_date', 'estimated_hours', 'suggested_start_time']
        widgets = {
            'category': forms.HiddenInput(),  # Hidden, will be set by category_text
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Add description or notes...'
            }),
            'client': forms.Select(attrs={
                'class': 'form-select',
                'style': 'width: 100%; min-width: 350px;'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.25',
                'placeholder': 'Estimated hours to complete'
            }),
            'suggested_start_time': forms.HiddenInput(),  # Hidden field for suggested time from slot finder
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.user = user  # Store user for later use in save()
        
        # Filter clients to current user only
        if user:
            self.fields['client'].queryset = self.fields['client'].queryset.filter(user=user)
            
            # Pre-populate category_text if editing existing event
            if self.instance and self.instance.category:
                self.fields['category_text'].initial = self.instance.category.name
                self.fields['category'].initial = self.instance.category.id
    def save(self, commit=True):
        """Save the event: handle category creation and store description"""
        event = super().save(commit=False)
        
        if self.user:
            event.user = self.user
            
            # Get or create category from category_text
            category_name = self.cleaned_data.get('category_text', '').strip()
            if category_name:
                category, created = WorkCategory.objects.get_or_create(
                    user=self.user,
                    name=category_name,
                )
                event.category = category
                
                # Optionally store description in metadata (for future enhancement)
                # For now, it's stored in event.description field
        
        if commit:
            event.save()
        return event
