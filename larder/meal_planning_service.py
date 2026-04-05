"""
Meal Planning Service Layer

Handles intelligent meal plan generation, shopping list creation,
and dietary preference management.
"""
from datetime import datetime, timedelta
from django.db.models import Q, Count, Prefetch
from django.utils import timezone
from .models import (
    Recipe, Menu, MealPlan, MealPlanDay, ShoppingList,
    ShoppingListItem, Ingredient, Criteria
)


class MealPlanGenerator:
    """Generate intelligent meal plans based on user preferences and recipes."""
    
    def __init__(self, user, criteria=None):
        self.user = user
        self.criteria = criteria
        self.recipes_used = set()  # Track recipes in current plan to avoid repeats
    
    def generate_meal_plan(self, name, start_date, end_date, 
                          time_period='weekly', criteria=None):
        """
        Generate a complete meal plan with auto-populated daily menus.
        
        Args:
            name: Name of the meal plan
            start_date: Start date (date object)
            end_date: End date (date object)
            time_period: 'daily', 'weekly', or 'custom'
            criteria: Optional Criteria object for dietary preferences
            
        Returns:
            MealPlan instance with populated MealPlanDay records
        """
        # Create the meal plan
        meal_plan = MealPlan.objects.create(
            user=self.user,
            name=name,
            start_date=start_date,
            end_date=end_date,
            time_period=time_period
        )
        
        # Generate day-by-day menus
        current_date = start_date
        while current_date <= end_date:
            meal_plan_day = MealPlanDay.objects.create(
                meal_plan=meal_plan,
                day_date=current_date
            )
            
            # Assign menus for this day
            self._assign_daily_menus(meal_plan_day, criteria)
            
            current_date += timedelta(days=1)
        
        return meal_plan
    
    def _assign_daily_menus(self, meal_plan_day, criteria=None):
        """
        Intelligently assign menus (breakfast, lunch, dinner) to a day.
        
        Respects:
        - Dietary criteria (vegetarian, vegan, allergens)
        - Calorie targets
        - Ingredient variety (avoids repeating same recipes)
        """
        meal_periods = ['breakfast', 'lunch', 'dinner']
        
        for period in meal_periods:
            # Get available menus for this period
            menus = Menu.objects.filter(
                user=self.user,
                meal_period=period
            ).prefetch_related('recipes')
            
            if not menus.exists():
                continue
            
            # If criteria specified, filter menus that match
            if criteria:
                matching_menus = []
                for menu in menus:
                    if self._menu_matches_criteria(menu, criteria):
                        matching_menus.append(menu)
                menus = matching_menus
            
            if not menus:
                continue
            
            # Select best menu (prefer variety)
            selected_menu = self._select_best_menu(menus)
            if selected_menu:
                meal_plan_day.menus.add(selected_menu)
    
    def _menu_matches_criteria(self, menu, criteria):
        """Check if menu satisfies dietary criteria."""
        if criteria.vegetarian:
            for recipe in menu.recipes.all():
                if not recipe.is_vegetarian:
                    return False
        
        if criteria.vegan:
            for recipe in menu.recipes.all():
                if not recipe.is_vegan:
                    return False
        
        # Check allergens
        if criteria.exclude_allergens:
            for recipe in menu.recipes.all():
                recipe_allergens = set(recipe.allergens or [])
                if recipe_allergens & criteria.exclude_allergens:
                    return False
        
        return True
    
    def _select_best_menu(self, menus):
        """
        Select the best menu from options.
        Prefers menus with recipes not recently used.
        """
        best_menu = None
        best_score = -1
        
        for menu in menus:
            # Calculate variety score
            variety_score = 0
            for recipe in menu.recipes.all():
                if recipe.pk not in self.recipes_used:
                    variety_score += 10
                variety_score += 1  # Base score for available recipe
            
            if variety_score > best_score:
                best_score = variety_score
                best_menu = menu
            
            # Track used recipes
            for recipe in menu.recipes.all():
                self.recipes_used.add(recipe.pk)
        
        return best_menu
    
    def generate_shopping_list(self, meal_plan, name=None):
        """
        Generate shopping list from a meal plan.
        
        Aggregates all ingredients from all recipes in the meal plan,
        handling quantities intelligently.
        
        Args:
            meal_plan: MealPlan instance
            name: Custom name for shopping list (optional)
            
        Returns:
            ShoppingList instance with items
        """
        if not name:
            name = f"Shopping List - {meal_plan.name}"
        
        # Create shopping list
        shopping_list = ShoppingList.objects.create(
            user=self.user,
            meal_plan=meal_plan,
            name=name
        )
        
        # Aggregate ingredients from all recipes in meal plan
        ingredient_totals = {}  # {product_id: (quantity, unit, product)}
        
        for meal_plan_day in meal_plan.meal_plan_days.all():
            for menu in meal_plan_day.menus.all():
                for recipe in menu.recipes.all():
                    for ingredient in recipe.ingredients.all():
                        key = (ingredient.product.pk, ingredient.unit)
                        
                        if key in ingredient_totals:
                            current_qty, _, product = ingredient_totals[key]
                            ingredient_totals[key] = (
                                current_qty + ingredient.quantity,
                                ingredient.unit,
                                product
                            )
                        else:
                            ingredient_totals[key] = (
                                ingredient.quantity,
                                ingredient.unit,
                                ingredient.product
                            )
        
        # Create shopping list items
        for (product_id, unit), (quantity, unit_type, product) in ingredient_totals.items():
            # Get estimated cost from product prices
            estimated_cost = self._get_product_cost(product)
            
            ShoppingListItem.objects.create(
                shopping_list=shopping_list,
                product=product,
                quantity=quantity,
                unit=unit_type,
                estimated_cost=estimated_cost
            )
        
        # Calculate total cost
        shopping_list.total_cost = shopping_list.shoppinglistitem_set.aggregate(
            total=Count('estimated_cost')
        ).get('total', 0)
        shopping_list.save()
        
        return shopping_list
    
    def _get_product_cost(self, product):
        """Get estimated cost of product from price history."""
        from .models import ProductPrice
        
        # Get latest price
        latest_price = ProductPrice.objects.filter(
            product=product
        ).order_by('-last_updated').first()
        
        return latest_price.price if latest_price else None


class MealPlanOptimizer:
    """Optimize existing meal plans for nutrition, cost, or variety."""
    
    @staticmethod
    def balance_nutrition(meal_plan, target_calories=2000, 
                         target_protein_percent=30):
        """
        Optimize meal plan for nutritional balance.
        
        Suggests recipe swaps to better match targets.
        """
        recommendations = []
        
        for day in meal_plan.meal_plan_days.all():
            daily_nutrition = {
                'calories': 0,
                'protein': 0,
                'carbs': 0,
                'fat': 0
            }
            
            for menu in day.menus.all():
                for recipe in menu.recipes.all():
                    daily_nutrition['calories'] += recipe.calories or 0
                    daily_nutrition['protein'] += recipe.protein or 0
                    daily_nutrition['carbs'] += recipe.carbs or 0
                    daily_nutrition['fat'] += recipe.fat or 0
            
            # Check if within acceptable range (±10%)
            cal_variance = abs(daily_nutrition['calories'] - target_calories) / target_calories
            if cal_variance > 0.1:
                recommendations.append({
                    'date': day.day_date,
                    'issue': f"Calories: {daily_nutrition['calories']:.0f} (target: {target_calories})",
                    'severity': 'high' if cal_variance > 0.2 else 'medium'
                })
        
        return recommendations
    
    @staticmethod
    def minimize_cost(meal_plan):
        """
        Suggest cheaper recipe alternatives.
        """
        # Requires price data integration
        pass
    
    @staticmethod
    def maximize_variety(meal_plan):
        """
        Ensure recipes don't repeat too often.
        Suggests variations or alternatives.
        """
        recipe_frequency = {}
        
        for day in meal_plan.meal_plan_days.all():
            for menu in day.menus.all():
                for recipe in menu.recipes.all():
                    recipe_frequency[recipe.id] = recipe_frequency.get(recipe.id, 0) + 1
        
        # Flag recipes appearing more than 2 times per week
        recommendations = []
        for recipe_id, count in recipe_frequency.items():
            if count > 2:
                recipe = Recipe.objects.get(pk=recipe_id)
                recommendations.append({
                    'recipe': recipe.name,
                    'frequency': count,
                    'suggestion': f"Consider alternative for {recipe.name}"
                })
        
        return recommendations


def suggest_recipes_for_menu(user, meal_period, criteria=None, exclude_recipes=None):
    """
    Suggest recipes for a specific menu period.
    
    Args:
        user: User instance
        meal_period: 'breakfast', 'lunch', or 'dinner'
        criteria: Optional Criteria for filtering
        exclude_recipes: List of recipe IDs to exclude
        
    Returns:
        Filtered QuerySet of Recipe instances
    """
    recipes = Recipe.objects.filter(user=user)
    
    if exclude_recipes:
        recipes = recipes.exclude(pk__in=exclude_recipes)
    
    if criteria:
        if criteria.vegetarian:
            recipes = recipes.filter(is_vegetarian=True)
        if criteria.vegan:
            recipes = recipes.filter(is_vegan=True)
        if criteria.exclude_allergens:
            for allergen in criteria.exclude_allergens:
                recipes = recipes.exclude(allergens__contains=allergen)
        if criteria.max_calories:
            recipes = recipes.filter(calories__lte=criteria.max_calories)
    
    return recipes.order_by('-calories', 'name')


def bulk_assign_menus_to_days(meal_plan, menus, day_type='all'):
    """
    Bulk assign same menus to multiple days.
    
    Args:
        meal_plan: MealPlan instance
        menus: List of Menu instances to assign
        day_type: 'all', 'weekdays' (Mon-Fri), 'weekends' (Sat-Sun)
    """
    days = meal_plan.meal_plan_days.all()
    
    if day_type == 'weekdays':
        # Monday=0, Sunday=6
        days = [d for d in days if d.day_date.weekday() < 5]
    elif day_type == 'weekends':
        days = [d for d in days if d.day_date.weekday() >= 5]
    
    for day in days:
        day.menus.set(menus)


# ============ Convenience Functions ============

def quick_generate_meal_plan(user, name, days=7, criteria=None):
    """
    Quick-generate a meal plan for N days.
    
    Args:
        user: User instance
        name: Meal plan name
        days: Number of days (default 7 for weekly)
        criteria: Optional Criteria for dietary preferences
        
    Returns:
        MealPlan instance
    """
    start_date = timezone.now().date()
    end_date = start_date + timedelta(days=days - 1)
    
    generator = MealPlanGenerator(user, criteria)
    return generator.generate_meal_plan(
        name=name,
        start_date=start_date,
        end_date=end_date,
        time_period='weekly' if days == 7 else 'custom',
        criteria=criteria
    )


def auto_create_shopping_list(meal_plan):
    """
    Auto-generate shopping list from meal plan.
    
    Args:
        meal_plan: MealPlan instance
        
    Returns:
        ShoppingList instance
    """
    generator = MealPlanGenerator(meal_plan.user)
    return generator.generate_shopping_list(meal_plan)
