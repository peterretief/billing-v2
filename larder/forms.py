from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
from .models import (
    Recipe, Ingredient, Criteria, Menu, MealPlan, MealPlanDay,
    ShoppingList, Order, ProductMaster
)

User = get_user_model()


class RecipeForm(forms.ModelForm):
    """Form for creating/editing recipes."""
    ingredients = forms.ModelMultipleChoiceField(
        queryset=Ingredient.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select ingredients for this recipe"
    )
    
    class Meta:
        model = Recipe
        fields = [
            'name', 'description', 'calories', 'protein_g', 'carbs_g',
            'fat_g', 'is_vegetarian', 'is_vegan', 'allergens',
            'prep_time_minutes', 'cook_time_minutes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Recipe name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Recipe description'}),
            'calories': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Calories per serving'}),
            'protein_g': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Protein (g)'}),
            'carbs_g': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Carbs (g)'}),
            'fat_g': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Fat (g)'}),
            'is_vegetarian': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_vegan': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allergens': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter allergens as comma-separated list (e.g., nuts, dairy)'}),
            'prep_time_minutes': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Prep time (minutes)'}),
            'cook_time_minutes': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Cook time (minutes)'}),
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['ingredients'].queryset = Ingredient.objects.filter(user=user)
    
    def clean_allergens(self):
        """Convert comma-separated allergens to list."""
        allergens = self.cleaned_data.get('allergens', '')
        if isinstance(allergens, str):
            return [a.strip().lower() for a in allergens.split(',') if a.strip()]
        return allergens


class IngredientForm(forms.ModelForm):
    """Form for creating/editing ingredients."""
    class Meta:
        model = Ingredient
        fields = ['product', 'quantity', 'unit']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Quantity'}),
            'unit': forms.Select(attrs={'class': 'form-control'}),
        }


class CriteriaForm(forms.ModelForm):
    """Form for creating/editing dietary criteria."""
    class Meta:
        model = Criteria
        fields = ['name', 'max_calories', 'vegetarian', 'vegan', 'exclude_allergens']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Criteria name (e.g., Low-Calorie Vegan)'}),
            'max_calories': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max calories per serving'}),
            'vegetarian': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'vegan': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'exclude_allergens': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Allergens to avoid (comma-separated)'}),
        }
    
    def clean_exclude_allergens(self):
        """Convert comma-separated allergens to list."""
        allergens = self.cleaned_data.get('exclude_allergens', '')
        if isinstance(allergens, str):
            return [a.strip().lower() for a in allergens.split(',') if a.strip()]
        return allergens


class MenuForm(forms.ModelForm):
    """Form for creating/editing menus."""
    recipes = forms.ModelMultipleChoiceField(
        queryset=Recipe.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select recipes for this menu"
    )
    
    class Meta:
        model = Menu
        fields = ['name', 'meal_period', 'criteria']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Menu name'}),
            'meal_period': forms.Select(attrs={'class': 'form-control'}),
            'criteria': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['recipes'].queryset = Recipe.objects.filter(user=user)
            self.fields['criteria'].queryset = Criteria.objects.filter(user=user)
            self.fields['criteria'].empty_label = "No specific criteria"


class MealPlanForm(forms.ModelForm):
    """Form for creating/editing meal plans."""
    class Meta:
        model = MealPlan
        fields = ['name', 'time_period', 'start_date', 'end_date', 'criteria']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Meal plan name'}),
            'time_period': forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'criteria': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['criteria'].queryset = Criteria.objects.filter(user=user)
            self.fields['criteria'].empty_label = "No specific criteria"
    
    def clean(self):
        """Validate date range."""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError("End date must be after start date.")
            if end_date < date.today():
                raise forms.ValidationError("Meal plan must be for future dates.")
        
        return cleaned_data


class MealPlanDayForm(forms.ModelForm):
    """Form for assigning menus to specific days in a meal plan."""
    menus = forms.ModelMultipleChoiceField(
        queryset=Menu.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select menus for this day"
    )
    
    class Meta:
        model = MealPlanDay
        fields = ['day_date']
        widgets = {
            'day_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
    
    def __init__(self, *args, meal_plan=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['menus'].queryset = Menu.objects.filter(user=user)
        if meal_plan:
            self.meal_plan = meal_plan
            # Validate day_date is within meal plan range
            self.fields['day_date'].widget.attrs['min'] = str(meal_plan.start_date)
            self.fields['day_date'].widget.attrs['max'] = str(meal_plan.end_date)
    
    def clean_day_date(self):
        """Validate day is within meal plan date range."""
        day_date = self.cleaned_data.get('day_date')
        if hasattr(self, 'meal_plan'):
            if day_date and (day_date < self.meal_plan.start_date or day_date > self.meal_plan.end_date):
                raise forms.ValidationError(
                    f"Day must be between {self.meal_plan.start_date} and {self.meal_plan.end_date}."
                )
        return day_date


class ShoppingListForm(forms.ModelForm):
    """Form for managing shopping lists."""
    class Meta:
        model = ShoppingList
        fields = ['name', 'is_purchased']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Shopping list name'}),
            'is_purchased': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, meal_plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        if meal_plan and not self.instance.pk:
            self.fields['name'].initial = f"{meal_plan.name} - Shopping List"


class ShoppingListFilterForm(forms.Form):
    """Form for filtering items on shopping list."""
    CATEGORY_CHOICES = [
        ('', 'All categories'),
        ('produce', 'Produce'),
        ('dairy', 'Dairy'),
        ('meat', 'Meat & Fish'),
        ('pantry', 'Pantry'),
        ('frozen', 'Frozen'),
        ('other', 'Other'),
    ]
    
    category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search items...'})
    )
    purchased_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Show purchased items only'
    )


class OrderForm(forms.ModelForm):
    """Form for creating/editing orders."""
    class Meta:
        model = Order
        fields = ['store', 'status', 'notes']
        widgets = {
            'store': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes for this order...'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import GroceryStore
        self.fields['store'].queryset = GroceryStore.objects.all()


class MealPlanQuickCreateForm(forms.Form):
    """Quick form for generating a meal plan."""
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Meal plan name'}),
        help_text="e.g., Weekly Budget Plan, Keto Week 1"
    )
    
    time_period = forms.ChoiceField(
        choices=MealPlan.TIME_PERIOD_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        help_text="How long should this meal plan last?"
    )
    
    duration_days = forms.IntegerField(
        initial=7,
        min_value=1,
        max_value=90,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Number of days (1-90)"
    )
    
    criteria = forms.ModelChoiceField(
        queryset=Criteria.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Apply dietary criteria (optional)"
    )
    
    auto_generate = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Auto-generate menus for each day"
    )
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['criteria'].queryset = Criteria.objects.filter(user=user)
            self.fields['criteria'].empty_label = "No specific criteria"


class BulkMenuAssignmentForm(forms.Form):
    """Form for bulk assigning menus to multiple days."""
    menu = forms.ModelChoiceField(
        queryset=Menu.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Select menu to assign"
    )
    
    days_pattern = forms.ChoiceField(
        choices=[
            ('all', 'All days in meal plan'),
            ('weekdays', 'Weekdays only (Mon-Fri)'),
            ('weekends', 'Weekends only (Sat-Sun)'),
            ('specific', 'Specific day of week'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        help_text="Which days should this menu appear?"
    )
    
    day_of_week = forms.ChoiceField(
        choices=[(i, d) for i, d in enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Only used if 'Specific day of week' is selected"
    )
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['menu'].queryset = Menu.objects.filter(user=user)
