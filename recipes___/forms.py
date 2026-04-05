from decimal import Decimal

from django import forms

from .models import Ingredient, LarderItem, PriceSource, Recipe, UserPreference


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = [
            "is_vegetarian", "is_vegan", "is_halal",
            "is_gluten_free", "is_dairy_free", "is_nut_free",
            "servings", "preferred_cuisines", "excluded_ingredients",
        ]
        widgets = {
            "preferred_cuisines": forms.TextInput(attrs={"placeholder": "e.g. Italian, Asian, Mediterranean"}),
            "excluded_ingredients": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["excluded_ingredients"].queryset = Ingredient.objects.filter(user=user)


class MealPlanGenerateForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Week of April 2026"}),
        help_text="Leave blank to auto-generate a title.",
    )
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end:
            if end < start:
                raise forms.ValidationError("End date must be on or after start date.")
            if (end - start).days > 365:
                raise forms.ValidationError("Date range cannot exceed 365 days.")
        return cleaned

    def get_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            start = self.cleaned_data["start_date"]
            end = self.cleaned_data["end_date"]
            title = f"Meal Plan {start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
        return title


class SwapMealForm(forms.Form):
    SLOT_CHOICES = [("breakfast", "Breakfast"), ("lunch", "Lunch"), ("dinner", "Dinner")]
    slot = forms.ChoiceField(choices=SLOT_CHOICES)
    recipe_id = forms.IntegerField()

    def get_recipe(self, user):
        return Recipe.objects.get(pk=self.cleaned_data["recipe_id"], user=user)


class LarderItemForm(forms.ModelForm):
    class Meta:
        model = LarderItem
        fields = ["ingredient", "name", "quantity", "unit", "expiry_date", "is_staple", "cost_per_unit", "notes"]
        widgets = {
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.TextInput(attrs={"placeholder": "Optional note (e.g. opened, half bag)"}),
        }
        help_texts = {
            "ingredient": "Optional — link to catalog for automatic cost data.",
            "is_staple": "Check for pantry basics (oil, salt, flour) that are always available.",
            "cost_per_unit": "Helps the AI prioritise expensive items near expiry.",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["ingredient"].queryset = Ingredient.objects.filter(user=user)
        self.fields["ingredient"].required = False
        self.fields["expiry_date"].required = False
        self.fields["notes"].required = False
        self.fields["cost_per_unit"].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Auto-fill name from linked ingredient if name is blank
        if not instance.name and instance.ingredient:
            instance.name = instance.ingredient.name
        # Auto-fill cost from ingredient catalog if not set
        if instance.ingredient and instance.cost_per_unit == 0:
            ing = instance.ingredient
            if ing.purchase_quantity > 0:
                instance.cost_per_unit = ing.purchase_value / ing.purchase_quantity
        if commit:
            instance.save()
        return instance


class PriceSourceForm(forms.ModelForm):
    class Meta:
        model = PriceSource
        fields = ["name", "url", "notes", "is_active"]
        widgets = {
            "url": forms.URLInput(attrs={"placeholder": "https://www.example.co.za/prices/"}),
            "notes": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "e.g. 'Prices listed in ZAR per kg. Table has columns: Item, Grade, Price.'",
            }),
        }


class LarderConsumeForm(forms.Form):
    qty_used = forms.DecimalField(
        min_value=Decimal("0.001"),
        decimal_places=3,
        label="Quantity used",
        widget=forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
    )
