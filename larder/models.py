from django.db import models
from django.conf import settings
from core.models import TenantModel


class GroceryStore(models.Model):
    """Global: Grocery chains available to all users."""
    name = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.name

class ProductMaster(models.Model):
    """Global: Shared barcode registry to prevent redundant data entry."""
    barcode = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=100, blank=True)
    
    # Flexible storage for health/nutrition (e.g., {"calories": 200, "protein": "10g"})
    nutrition_data = models.JSONField(default=dict, blank=True)
    
    # Metadata for AI/Categorization (e.g., {"is_staple": True, "category": "Dairy"})
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.name} ({self.barcode})"

    @property
    def quality_score(self):
        """
        Calculates a quality score (0-100) based on Nutri-Score and NOVA group.
        """
        score = 50 # Base score
        
        # Nutri-score adjustment
        nutriscore = self.metadata.get('nutriscore', '').lower()
        ns_map = {'a': 25, 'b': 15, 'c': 5, 'd': -10, 'e': -25}
        score += ns_map.get(nutriscore, 0)
        
        # NOVA group adjustment (1=unprocessed, 4=ultra-processed)
        nova = self.metadata.get('nova_group')
        if nova == 1: score += 25
        elif nova == 2: score += 10
        elif nova == 3: score -= 10
        elif nova == 4: score -= 25
        
        return max(0, min(100, score))

class ProductPrice(models.Model):
    """Tracks specific prices for a product at different stores."""
    product = models.ForeignKey(ProductMaster, on_delete=models.CASCADE, related_name='prices')
    store = models.ForeignKey(GroceryStore, on_delete=models.CASCADE, related_name='product_prices')
    
    price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_size = models.DecimalField(max_digits=10, decimal_places=2, help_text="e.g. 500 for 500g")
    unit_type = models.CharField(max_length=20, choices=[('g', 'Grams'), ('kg', 'Kilograms'), ('ml', 'Milliliters'), ('l', 'Liters'), ('unit', 'Units')], default='g')
    
    is_on_sale = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'store')
        ordering = ['price']

    def __str__(self):
        return f"{self.product.name} at {self.store.name}: {self.price}"

    @property
    def price_per_standard_unit(self):
        """Calculates price per 100g/ml or per 1 unit."""
        if self.unit_size == 0:
            return 0
            
        if self.unit_type in ['kg', 'l']:
            # Convert to g/ml base (1000) then get price per 100
            base_size = self.unit_size * 1000
            return (self.price / base_size) * 100
        elif self.unit_type == 'unit':
            return self.price / self.unit_size
        else:
            # Already in g/ml, get price per 100
            return (self.price / self.unit_size) * 100

class LarderItem(TenantModel):
    product = models.ForeignKey(ProductMaster, on_delete=models.CASCADE)
    store = models.ForeignKey(GroceryStore, on_delete=models.SET_NULL, null=True)
    
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.0)
    unit = models.CharField(max_length=20, default="units") 
    price_paid = models.DecimalField(max_digits=10, decimal_places=2) 
    
    # Indexed for faster "Expiring Soon" lookups
    expiry_date = models.DateField(db_index=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    is_consumed = models.BooleanField(default=False)

    class Meta:
        # This keeps the "garbage" out by ensuring you don't 
        # accidentally mix tenant data in raw queries
        ordering = ['expiry_date']

    @property
    def is_expired(self):
        from datetime import date
        return self.expiry_date < date.today()


class Ingredient(TenantModel):
    """Ingredient used in recipes."""
    product = models.ForeignKey(ProductMaster, on_delete=models.CASCADE, related_name='ingredients')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(
        max_length=20,
        choices=[('g', 'Grams'), ('kg', 'Kilograms'), ('ml', 'Milliliters'), ('l', 'Liters'), ('unit', 'Units'), ('tbsp', 'Tablespoon'), ('tsp', 'Teaspoon'), ('cup', 'Cup')],
        default='g'
    )
    
    class Meta:
        ordering = ['product__name']
        unique_together = ('user', 'product')
    
    def __str__(self):
        return f"{self.product.name} ({self.quantity}{self.unit})"


class Recipe(TenantModel):
    """Recipe with ingredients and nutritional information."""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    ingredients = models.ManyToManyField(Ingredient, related_name='recipes')
    
    # Nutritional info per serving
    calories = models.IntegerField(null=True, blank=True)
    protein_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    carbs_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    fat_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    
    # Tags/Categories
    is_vegetarian = models.BooleanField(default=False)
    is_vegan = models.BooleanField(default=False)
    allergens = models.JSONField(default=list, help_text="List of allergens: ['nuts', 'dairy', 'gluten', etc]")
    
    prep_time_minutes = models.IntegerField(null=True, blank=True)
    cook_time_minutes = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['user', 'is_vegetarian']),
            models.Index(fields=['user', 'is_vegan']),
        ]
    
    def __str__(self):
        return self.name
    
    def total_time_minutes(self):
        """Total prep + cook time."""
        prep = self.prep_time_minutes or 0
        cook = self.cook_time_minutes or 0
        return prep + cook
    
    def matches_criteria(self, max_calories=None, vegetarian=False, vegan=False, exclude_allergens=None):
        """Check if recipe matches dietary criteria."""
        if max_calories and self.calories and self.calories > max_calories:
            return False
        if vegetarian and not self.is_vegetarian:
            return False
        if vegan and not self.is_vegan:
            return False
        if exclude_allergens:
            for allergen in exclude_allergens:
                if allergen in self.allergens:
                    return False
        return True


class Criteria(TenantModel):
    """Dietary & preference criteria for recipe filtering."""
    name = models.CharField(max_length=100)
    max_calories = models.IntegerField(null=True, blank=True)
    vegetarian = models.BooleanField(default=False)
    vegan = models.BooleanField(default=False)
    exclude_allergens = models.JSONField(default=list, help_text="Allergens to avoid")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Criteria'
        unique_together = ('user', 'name')
    
    def __str__(self):
        return self.name
    
    def get_matching_recipes(self):
        """Get recipes matching this criteria."""
        recipes = Recipe.objects.filter(user=self.user)
        filtered = []
        for recipe in recipes:
            if recipe.matches_criteria(
                max_calories=self.max_calories,
                vegetarian=self.vegetarian,
                vegan=self.vegan,
                exclude_allergens=self.exclude_allergens
            ):
                filtered.append(recipe)
        return filtered


class Menu(TenantModel):
    """Menu for a specific time period (Breakfast, Lunch, Supper)."""
    MEAL_PERIOD_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
    ]
    
    name = models.CharField(max_length=100)
    meal_period = models.CharField(max_length=20, choices=MEAL_PERIOD_CHOICES)
    recipes = models.ManyToManyField(Recipe, related_name='menus', through='MenuRecipe')
    
    criteria = models.ForeignKey(
        Criteria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional criteria to guide recipe selection"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['meal_period', 'name']
        unique_together = ('user', 'name')
    
    def __str__(self):
        return f"{self.name} ({self.get_meal_period_display()})"


class MenuRecipe(models.Model):
    """Through table for Menu-Recipe relationship with ordering."""
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        unique_together = ('menu', 'recipe')
    
    def __str__(self):
        return f"{self.menu.name} - {self.recipe.name}"


class MealPlan(TenantModel):
    """Meal plan for a time period (weekly or daily)."""
    TIME_PERIOD_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('custom', 'Custom'),
    ]
    
    name = models.CharField(max_length=255)
    time_period = models.CharField(max_length=20, choices=TIME_PERIOD_CHOICES, default='weekly')
    start_date = models.DateField()
    end_date = models.DateField()
    
    criteria = models.ForeignKey(
        Criteria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Overall criteria for this meal plan"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['user', 'start_date']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"
    
    def get_days_count(self):
        """Number of days in this meal plan."""
        return (self.end_date - self.start_date).days + 1
    
    def get_all_ingredients(self):
        """Get all unique ingredients needed for this meal plan."""
        ingredients = set()
        for day in self.meal_plan_days.all():
            for menu in day.menus.all():
                for recipe in menu.recipes.all():
                    for ingredient in recipe.ingredients.all():
                        ingredients.add(ingredient.product)
        return ingredients


class MealPlanDay(models.Model):
    """Maps specific menus to days in a meal plan."""
    meal_plan = models.ForeignKey(
        MealPlan,
        on_delete=models.CASCADE,
        related_name='meal_plan_days'
    )
    day_date = models.DateField()
    menus = models.ManyToManyField(Menu, related_name='meal_plan_days')
    
    class Meta:
        ordering = ['day_date']
        unique_together = ('meal_plan', 'day_date')
    
    def __str__(self):
        return f"{self.meal_plan.name} - {self.day_date}"


class ShoppingList(TenantModel):
    """Auto-generated shopping list from a meal plan."""
    meal_plan = models.ForeignKey(
        MealPlan,
        on_delete=models.CASCADE,
        related_name='shopping_lists'
    )
    name = models.CharField(max_length=255)
    
    is_purchased = models.BooleanField(default=False)
    purchased_at = models.DateTimeField(null=True, blank=True)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'meal_plan')
    
    def __str__(self):
        return f"{self.name} ({self.meal_plan.name})"
    
    def get_items(self):
        """Get aggregated shopping items from all recipes in meal plan."""
        items = {}
        for day in self.meal_plan.meal_plan_days.all():
            for menu in day.menus.all():
                for recipe in menu.recipes.all():
                    for menu_recipe in recipe.menurecipe_set.filter(menu=menu):
                        for ingredient in recipe.ingredients.all():
                            key = ingredient.product.id
                            if key not in items:
                                items[key] = {
                                    'product': ingredient.product,
                                    'total_quantity': 0,
                                    'unit': ingredient.unit
                                }
                            items[key]['total_quantity'] += ingredient.quantity
        return list(items.values())


class Order(TenantModel):
    """Order placed for shopping list items."""
    ORDER_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    shopping_list = models.ForeignKey(
        ShoppingList,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='draft')
    
    store = models.ForeignKey(
        GroceryStore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Store to order from"
    )
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    ordered_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'ordered_at']),
        ]
    
    def __str__(self):
        return f"Order {self.id} - {self.get_status_display()}"
    
    def place_order(self):
        """Mark order as placed."""
        from django.utils import timezone
        self.status = 'confirmed'
        self.ordered_at = timezone.now()
        self.save()
    
    def mark_delivered(self):
        """Mark order as delivered."""
        from django.utils import timezone
        self.status = 'delivered'
        self.delivered_at = timezone.now()
        self.save()


class ShoppingListItem(models.Model):
    """Individual items in a shopping list."""
    shopping_list = models.ForeignKey(
        ShoppingList,
        on_delete=models.CASCADE,
        related_name='shoppinglistitem_set'
    )
    
    product = models.ForeignKey(
        ProductMaster,
        on_delete=models.CASCADE,
        related_name='shopping_list_items'
    )
    
    quantity = models.DecimalField(max_digits=8, decimal_places=2)
    unit = models.CharField(
        max_length=20,
        default='unit',
        help_text="g, kg, ml, l, unit, etc."
    )
    
    estimated_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    purchased = models.BooleanField(default=False)
    purchased_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['product__name']
        unique_together = ('shopping_list', 'product')
    
    def __str__(self):
        return f"{self.product.name} ({self.quantity} {self.unit})"
    
    def mark_purchased(self):
        """Mark item as purchased."""
        from django.utils import timezone
        self.purchased = True
        self.purchased_at = timezone.now()
        self.save()
        self.save()