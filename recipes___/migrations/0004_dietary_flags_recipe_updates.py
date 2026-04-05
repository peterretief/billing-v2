from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0003_ingredient_inventory_item"),
    ]

    operations = [
        # --- RecipeTag table ---
        migrations.CreateModel(
            name="RecipeTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50, unique=True)),
                ("slug", models.SlugField(unique=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        # --- Dietary flags on Ingredient ---
        migrations.AddField(
            model_name="ingredient",
            name="is_vegetarian",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="ingredient",
            name="is_vegan",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="ingredient",
            name="is_halal",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="ingredient",
            name="is_gluten_free",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="ingredient",
            name="is_dairy_free",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="ingredient",
            name="is_nut_free",
            field=models.BooleanField(default=True),
        ),
        # --- meal_type and dietary flags on Recipe ---
        migrations.AddField(
            model_name="recipe",
            name="meal_type",
            field=models.CharField(
                choices=[
                    ("breakfast", "Breakfast"),
                    ("lunch", "Lunch"),
                    ("dinner", "Dinner"),
                    ("snack", "Snack"),
                    ("any", "Any Meal"),
                ],
                default="any",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="recipe",
            name="is_vegetarian",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="recipe",
            name="is_vegan",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="recipe",
            name="is_halal",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="recipe",
            name="is_gluten_free",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="recipe",
            name="is_dairy_free",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="recipe",
            name="is_nut_free",
            field=models.BooleanField(default=False),
        ),
        # --- Recipe ↔ RecipeTag M2M ---
        migrations.AddField(
            model_name="recipe",
            name="tags",
            field=models.ManyToManyField(
                blank=True,
                related_name="recipes",
                to="recipes.recipetag",
            ),
        ),
    ]
