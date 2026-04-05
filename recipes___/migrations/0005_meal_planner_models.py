import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0004_dietary_flags_recipe_updates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- UserPreference ---
        migrations.CreateModel(
            name="UserPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recipe_preference",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("is_vegetarian", models.BooleanField(default=False, verbose_name="Vegetarian")),
                ("is_vegan", models.BooleanField(default=False, verbose_name="Vegan")),
                ("is_halal", models.BooleanField(default=False, verbose_name="Halal")),
                ("is_gluten_free", models.BooleanField(default=False, verbose_name="Gluten Free")),
                ("is_dairy_free", models.BooleanField(default=False, verbose_name="Dairy Free")),
                ("is_nut_free", models.BooleanField(default=False, verbose_name="Nut Free")),
                ("servings", models.PositiveIntegerField(default=2, help_text="Number of people to cook for")),
                (
                    "preferred_cuisines",
                    models.CharField(
                        blank=True,
                        help_text="Comma-separated list of preferred cuisines (e.g. Italian, Asian, Mediterranean)",
                        max_length=500,
                    ),
                ),
                (
                    "excluded_ingredients",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific ingredients to exclude from all meal plans",
                        related_name="excluded_by_users",
                        to="recipes.ingredient",
                    ),
                ),
            ],
        ),
        # --- MealPlan ---
        migrations.CreateModel(
            name="MealPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mealplan_related",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("notes", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["-start_date"],
            },
        ),
        # --- MealPlanDay ---
        migrations.CreateModel(
            name="MealPlanDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "meal_plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="days",
                        to="recipes.mealplan",
                    ),
                ),
                ("date", models.DateField()),
                (
                    "breakfast",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="breakfast_days",
                        to="recipes.recipe",
                    ),
                ),
                (
                    "lunch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lunch_days",
                        to="recipes.recipe",
                    ),
                ),
                (
                    "dinner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dinner_days",
                        to="recipes.recipe",
                    ),
                ),
            ],
            options={
                "ordering": ["date"],
                "unique_together": {("meal_plan", "date")},
            },
        ),
        # --- ShoppingList ---
        migrations.CreateModel(
            name="ShoppingList",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shoppinglist_related",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "meal_plan",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shopping_list",
                        to="recipes.mealplan",
                    ),
                ),
                ("generated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "abstract": False,
            },
        ),
        # --- ShoppingListItem ---
        migrations.CreateModel(
            name="ShoppingListItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "shopping_list",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="recipes.shoppinglist",
                    ),
                ),
                (
                    "ingredient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="recipes.ingredient",
                    ),
                ),
                ("total_quantity", models.DecimalField(decimal_places=3, max_digits=10)),
                ("unit", models.CharField(max_length=50)),
                ("estimated_cost", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("store_source", models.CharField(blank=True, max_length=255)),
            ],
            options={
                "ordering": ["store_source", "ingredient__name"],
            },
        ),
    ]
