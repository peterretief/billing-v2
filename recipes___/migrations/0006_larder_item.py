import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0005_meal_planner_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LarderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="larderitem_related",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ingredient",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="larder_items",
                        to="recipes.ingredient",
                        help_text="Link to your ingredient catalog (optional — enables cost tracking).",
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=255, help_text="Display name of the item."),
                ),
                (
                    "quantity",
                    models.DecimalField(decimal_places=3, default=Decimal("1.000"), max_digits=10),
                ),
                ("unit", models.CharField(default="units", max_length=50)),
                (
                    "expiry_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        help_text="Leave blank for items without a meaningful expiry (e.g. dried pasta).",
                    ),
                ),
                (
                    "is_staple",
                    models.BooleanField(
                        default=False,
                        help_text="Staples (salt, oil, flour) are always assumed available and never trigger expiry alerts.",
                    ),
                ),
                (
                    "cost_per_unit",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=10,
                        help_text="Used to prioritise expensive items (meat, dairy) when they near expiry.",
                    ),
                ),
                ("notes", models.CharField(blank=True, max_length=500)),
            ],
            options={
                "ordering": ["is_staple", "expiry_date", "name"],
            },
        ),
    ]
