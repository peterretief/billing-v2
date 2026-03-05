from django import forms
from .models import Todo
from timesheets.models import WorkCategory


class TodoForm(forms.ModelForm):
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
        model = Todo
        fields = ['category', 'description', 'client', 'status', 'priority', 'due_date', 'estimated_hours']
        widgets = {
            'category': forms.HiddenInput(),  # Hidden, will be set by category_text
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Add description or notes...'
            }),
            'client': forms.Select(attrs={'class': 'form-select'}),
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
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.user = user  # Store user for later use in save()
        
        # Filter clients to current user only
        if user:
            self.fields['client'].queryset = self.fields['client'].queryset.filter(user=user)
            
            # Pre-populate category_text if editing existing todo
            if self.instance and self.instance.category:
                self.fields['category_text'].initial = self.instance.category.name
                self.fields['category'].initial = self.instance.category.id
    def save(self, commit=True):
        """Save the todo: handle category creation and store description"""
        todo = super().save(commit=False)
        
        if self.user:
            todo.user = self.user
            
            # Get or create category from category_text
            category_name = self.cleaned_data.get('category_text', '').strip()
            if category_name:
                category, created = WorkCategory.objects.get_or_create(
                    user=self.user,
                    name=category_name,
                )
                todo.category = category
                
                # Optionally store description in metadata (for future enhancement)
                # For now, it's stored in todo.description field
        
        if commit:
            todo.save()
        return todo
