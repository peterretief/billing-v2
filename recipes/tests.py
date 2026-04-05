from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import (
    Ingredient,
    MealPlan,
    MealPlanDay,
    Recipe,
    RecipeComponent,
    ShoppingList,
    ShoppingListItem,
    UserPreference,
    _filtered_recipes,
    generate_meal_plan,
    generate_shopping_list,
)

User = get_user_model()


def make_user(username="testchef"):
    return User.objects.create_user(username=username, email=f"{username}@example.com", password="pass")


def make_ingredient(user, name, vegetarian=True, vegan=True, gluten_free=True, dairy_free=True, nut_free=True):
    return Ingredient.objects.create(
        user=user, name=name,
        is_vegetarian=vegetarian, is_vegan=vegan,
        is_gluten_free=gluten_free, is_dairy_free=dairy_free, is_nut_free=nut_free,
        purchase_value=Decimal("10.00"), purchase_quantity=Decimal("1.000"), unit="kg",
    )


def make_recipe(user, name, meal_type="any", servings_yield=2, **dietary):
    defaults = {k: False for k in ("is_vegetarian", "is_vegan", "is_halal", "is_gluten_free", "is_dairy_free", "is_nut_free")}
    defaults.update(dietary)
    return Recipe.objects.create(user=user, name=name, meal_type=meal_type, servings_yield=servings_yield, **defaults)


class RecipeFilteringTest(TestCase):
    """Recipe filtering by dietary preference."""

    def setUp(self):
        self.user = make_user()
        self.pref = UserPreference.for_user(self.user)

        self.veg_recipe = make_recipe(self.user, "Veggie Stir Fry", is_vegetarian=True, meal_type="dinner")
        self.vegan_recipe = make_recipe(self.user, "Tofu Bowl", is_vegetarian=True, is_vegan=True, meal_type="dinner")
        self.meat_recipe = make_recipe(self.user, "Chicken Curry", meal_type="dinner")
        self.gf_recipe = make_recipe(self.user, "GF Pasta", is_gluten_free=True, meal_type="dinner")

    def test_no_filters_returns_all(self):
        qs = _filtered_recipes(self.user, self.pref, "dinner")
        self.assertEqual(qs.count(), 4)

    def test_vegetarian_filter(self):
        self.pref.is_vegetarian = True
        self.pref.save()
        qs = _filtered_recipes(self.user, self.pref, "dinner")
        names = list(qs.values_list("name", flat=True))
        self.assertIn("Veggie Stir Fry", names)
        self.assertIn("Tofu Bowl", names)
        self.assertNotIn("Chicken Curry", names)

    def test_vegan_filter(self):
        self.pref.is_vegan = True
        self.pref.save()
        qs = _filtered_recipes(self.user, self.pref, "dinner")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().name, "Tofu Bowl")

    def test_gluten_free_filter(self):
        self.pref.is_gluten_free = True
        self.pref.save()
        qs = _filtered_recipes(self.user, self.pref, "dinner")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().name, "GF Pasta")

    def test_meal_type_filter(self):
        make_recipe(self.user, "Pancakes", meal_type="breakfast", is_vegetarian=True)
        qs = _filtered_recipes(self.user, self.pref, "breakfast")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().name, "Pancakes")

    def test_any_meal_type_matches_all(self):
        """meal_type='any' recipes appear when filtering for a specific meal type."""
        # The 4 recipes in setUp are all meal_type='dinner' or 'any' depending on make_recipe defaults
        # Make one explicitly 'any'
        any_recipe = make_recipe(self.user, "Any Time Salad", meal_type="any")
        qs = _filtered_recipes(self.user, self.pref, "dinner")
        self.assertIn(any_recipe, list(qs))

    def test_excluded_ingredient_removes_recipe(self):
        bad_ing = make_ingredient(self.user, "Peanuts")
        RecipeComponent.objects.create(
            user=self.user, recipe=self.veg_recipe, ingredient=bad_ing, quantity_used=Decimal("0.1"),
        )
        self.pref.excluded_ingredients.add(bad_ing)
        qs = _filtered_recipes(self.user, self.pref, "dinner")
        self.assertNotIn(self.veg_recipe, list(qs))

    def test_data_isolation(self):
        """Recipes from another user are never returned."""
        other_user = make_user("other")
        make_recipe(other_user, "Other User Recipe", meal_type="dinner")
        qs = _filtered_recipes(self.user, self.pref, "dinner")
        names = list(qs.values_list("name", flat=True))
        self.assertNotIn("Other User Recipe", names)


class MealPlanGenerationTest(TestCase):
    """Meal plan generation: correct days, no intra-week same-slot repeats."""

    def setUp(self):
        self.user = make_user("planner")
        self.pref = UserPreference.for_user(self.user)

        for i in range(7):
            make_recipe(self.user, f"Breakfast {i}", meal_type="breakfast")
            make_recipe(self.user, f"Lunch {i}", meal_type="lunch")
            make_recipe(self.user, f"Dinner {i}", meal_type="dinner")

    def _plan(self, days=7):
        start = date(2026, 4, 7)
        end = start + timedelta(days=days - 1)
        return generate_meal_plan(self.user, "Test Plan", start, end)

    def test_correct_number_of_days(self):
        plan = self._plan(7)
        self.assertEqual(plan.days.count(), 7)

    def test_correct_number_of_days_month(self):
        plan = self._plan(30)
        self.assertEqual(plan.days.count(), 30)

    def test_each_day_has_all_slots(self):
        plan = self._plan(7)
        for day in plan.days.all():
            self.assertIsNotNone(day.breakfast, f"Missing breakfast on {day.date}")
            self.assertIsNotNone(day.lunch, f"Missing lunch on {day.date}")
            self.assertIsNotNone(day.dinner, f"Missing dinner on {day.date}")

    def test_no_same_day_slot_repeats_within_week(self):
        """Within the same 7-day window, no slot should repeat the same recipe."""
        plan = self._plan(7)
        days = list(plan.days.all())
        breakfasts = [d.breakfast_id for d in days if d.breakfast_id]
        lunches = [d.lunch_id for d in days if d.lunch_id]
        dinners = [d.dinner_id for d in days if d.dinner_id]
        self.assertEqual(len(breakfasts), len(set(breakfasts)))
        self.assertEqual(len(lunches), len(set(lunches)))
        self.assertEqual(len(dinners), len(set(dinners)))

    def test_meal_plan_belongs_to_user(self):
        plan = self._plan(7)
        self.assertEqual(plan.user, self.user)

    def test_single_day_plan(self):
        start = date(2026, 4, 7)
        plan = generate_meal_plan(self.user, "One Day", start, start)
        self.assertEqual(plan.days.count(), 1)

    def test_generates_with_no_matching_recipes(self):
        """Gracefully handles empty recipe pool — slots are None."""
        # All recipes are dinner type; filter for breakfast with no breakfast recipes
        pref = UserPreference.for_user(self.user)
        # Create a user with zero recipes
        empty_user = make_user("empty")
        UserPreference.for_user(empty_user)
        start = date(2026, 4, 7)
        plan = generate_meal_plan(empty_user, "Empty Plan", start, start + timedelta(days=2))
        self.assertEqual(plan.days.count(), 3)
        for day in plan.days.all():
            self.assertIsNone(day.breakfast)
            self.assertIsNone(day.lunch)
            self.assertIsNone(day.dinner)


class ShoppingListAggregationTest(TestCase):
    """Shopping list: correct aggregation, scaling, and store grouping."""

    def setUp(self):
        self.user = make_user("shopper")
        self.pref = UserPreference.for_user(self.user)
        self.pref.servings = 4
        self.pref.save()

        self.flour = make_ingredient(self.user, "Flour")
        self.flour.purchase_value = Decimal("20.00")
        self.flour.purchase_quantity = Decimal("2.000")
        self.flour.unit = "kg"
        self.flour.save()

        self.eggs = make_ingredient(self.user, "Eggs")
        self.eggs.purchase_value = Decimal("30.00")
        self.eggs.purchase_quantity = Decimal("12.000")
        self.eggs.unit = "units"
        self.eggs.save()

        # Recipe: serves 2, uses 0.5 kg flour + 3 eggs
        self.recipe = make_recipe(self.user, "Crepes", meal_type="breakfast")
        self.recipe.servings_yield = 2
        self.recipe.save()
        RecipeComponent.objects.create(user=self.user, recipe=self.recipe, ingredient=self.flour, quantity_used=Decimal("0.500"))
        RecipeComponent.objects.create(user=self.user, recipe=self.recipe, ingredient=self.eggs, quantity_used=Decimal("3.000"))

        # Plan: 2 days, breakfast = crepes, no lunch/dinner
        self.plan = MealPlan.objects.create(
            user=self.user, title="Test",
            start_date=date(2026, 4, 7), end_date=date(2026, 4, 8),
        )
        MealPlanDay.objects.create(meal_plan=self.plan, date=date(2026, 4, 7), breakfast=self.recipe)
        MealPlanDay.objects.create(meal_plan=self.plan, date=date(2026, 4, 8), breakfast=self.recipe)

    def test_shopping_list_created(self):
        sl = generate_shopping_list(self.plan)
        self.assertIsInstance(sl, ShoppingList)

    def test_correct_number_of_items(self):
        sl = generate_shopping_list(self.plan)
        # 2 distinct ingredients
        self.assertEqual(sl.items.count(), 2)

    def test_quantities_aggregated_and_scaled(self):
        """
        Servings = 4, recipe yields 2 → scale = 4/2 = 2.
        2 days × 0.5 kg flour × scale 2 = 2.000 kg flour.
        2 days × 3 eggs × scale 2 = 12 eggs.
        """
        sl = generate_shopping_list(self.plan)
        flour_item = sl.items.get(ingredient=self.flour)
        eggs_item = sl.items.get(ingredient=self.eggs)
        self.assertEqual(flour_item.total_quantity, Decimal("2.000"))
        self.assertEqual(eggs_item.total_quantity, Decimal("12.000"))

    def test_cost_calculated(self):
        """
        Flour: price_per_unit = 20/2 = 10/kg. 2 kg used → R 20.
        Eggs: price_per_unit = 30/12 = 2.5/unit. 12 used → R 30.
        Total = R 50.
        """
        sl = generate_shopping_list(self.plan)
        flour_item = sl.items.get(ingredient=self.flour)
        eggs_item = sl.items.get(ingredient=self.eggs)
        self.assertAlmostEqual(float(flour_item.estimated_cost), 20.0, places=2)
        self.assertAlmostEqual(float(eggs_item.estimated_cost), 30.0, places=2)

    def test_total_cost(self):
        sl = generate_shopping_list(self.plan)
        self.assertAlmostEqual(float(sl.total_cost), 50.0, places=2)

    def test_regenerate_replaces_old_list(self):
        sl1 = generate_shopping_list(self.plan)
        sl2 = generate_shopping_list(self.plan)
        self.assertNotEqual(sl1.pk, sl2.pk)
        self.assertEqual(ShoppingList.objects.filter(meal_plan=self.plan).count(), 1)

    def test_items_by_store_grouping(self):
        sl = generate_shopping_list(self.plan)
        # No market_ref → all items go to "General" group
        grouped = sl.items_by_store
        self.assertIn("General", grouped)
        self.assertEqual(len(grouped["General"]), 2)


class ShoppingListViewTest(TestCase):
    """Shopping list view: correct aggregation, scaling, and store grouping."""

    def setUp(self):
        self.user = make_user("viewer")
        self.client.force_login(self.user)
        
        self.flour = make_ingredient(self.user, "Flour")
        self.flour.purchase_value = Decimal("20.00")
        self.flour.purchase_quantity = Decimal("2.000")
        self.flour.unit = "kg"
        self.flour.save()

        # Recipe: serves 2, uses 0.5 kg flour
        self.recipe = make_recipe(self.user, "Crepes", meal_type="breakfast")
        self.recipe.servings_yield = 2
        self.recipe.save()
        RecipeComponent.objects.create(
            user=self.user, 
            recipe=self.recipe, 
            ingredient=self.flour, 
            quantity_used=Decimal("0.500")
        )

    def test_shopping_list_view_success(self):
        """Tests that the shopping list view calculates correctly without TypeError."""
        # headcount=10, servings_yield=2 -> factor=5.0
        # qty = 0.5 * 5.0 = 2.5
        response = self.client.get('/recipes/shopping-list/?headcount=10')
        self.assertEqual(response.status_code, 200)
        
        summary = response.context['summary']
        self.assertIn("Flour", summary)
        self.assertEqual(summary["Flour"]['qty'], Decimal("2.5"))


class MealPlanSwapViewTest(TestCase):
    """Meal plan swap view: correct rendering and swapping."""

    def setUp(self):
        self.user = make_user("swapper")
        self.client.force_login(self.user)
        
        self.recipe = make_recipe(self.user, "Test Recipe", meal_type="breakfast")
        
        self.plan = MealPlan.objects.create(
            user=self.user, title="Swap Plan",
            start_date=date(2026, 4, 7), end_date=date(2026, 4, 7),
        )
        self.day = MealPlanDay.objects.create(meal_plan=self.plan, date=date(2026, 4, 7))

    def test_meal_plan_swap_view_get(self):
        """Tests that the meal plan swap view renders without TemplateSyntaxError."""
        response = self.client.get(f'/recipes/meal-plan/{self.plan.pk}/day/{self.day.pk}/swap/?slot=breakfast')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Swap Meal")
        self.assertIn('current_recipe', response.context)

    def test_meal_plan_swap_view_post(self):
        """Tests that the meal plan swap view handles swapping recipes."""
        response = self.client.post(f'/recipes/meal-plan/{self.plan.pk}/day/{self.day.pk}/swap/', {
            'slot': 'breakfast',
            'recipe_id': self.recipe.pk
        })
        self.assertRedirects(response, f'/recipes/meal-plan/{self.plan.pk}/')
        self.day.refresh_from_db()
        self.assertEqual(self.day.breakfast, self.recipe)


class MealPlanDeleteViewTest(TestCase):
    """Meal plan delete view: correct deletion and redirection."""

    def setUp(self):
        self.user = make_user("deleter")
        self.client.force_login(self.user)
        self.plan = MealPlan.objects.create(
            user=self.user, title="Delete Me",
            start_date=date(2026, 4, 7), end_date=date(2026, 4, 7),
        )

    def test_meal_plan_delete_post(self):
        """Tests that a POST request deletes the meal plan."""
        response = self.client.post(f'/recipes/meal-plan/{self.plan.pk}/delete/')
        self.assertRedirects(response, '/recipes/meal-plans/')
        self.assertFalse(MealPlan.objects.filter(pk=self.plan.pk).exists())

    def test_meal_plan_delete_get_not_allowed(self):
        """Tests that a GET request does NOT delete the meal plan."""
        response = self.client.get(f'/recipes/meal-plan/{self.plan.pk}/delete/')
        self.assertRedirects(response, '/recipes/meal-plans/')
        self.assertTrue(MealPlan.objects.filter(pk=self.plan.pk).exists())


class MenuProcurementTest(TestCase):
    """Menu.generate_procurement_list: correct aggregation and scaling."""

    def setUp(self):
        self.user = make_user("menuchef")
        from .models import Menu
        self.flour = make_ingredient(self.user, "Flour")
        self.recipe = make_recipe(self.user, "Crepes", servings_yield=2)
        RecipeComponent.objects.create(
            user=self.user, 
            recipe=self.recipe, 
            ingredient=self.flour, 
            quantity_used=Decimal("0.500")
        )
        self.menu = Menu.objects.create(user=self.user, title="Breakfast Menu")
        self.menu.recipes.add(self.recipe)

    def test_menu_procurement_list_success(self):
        """Tests that Menu.generate_procurement_list calculates correctly without TypeError."""
        # headcount=10, servings_yield=2 -> factor=5.0
        # qty = 0.5 * 5.0 = 2.5
        summary = self.menu.generate_procurement_list(10)
        self.assertIn("Flour", summary)
        self.assertEqual(summary["Flour"]['qty'], Decimal("2.5"))
