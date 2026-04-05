import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0006_larder_item"),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
                ("url", models.URLField()),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        help_text="Optional hints for the AI parser (e.g. 'prices in ZAR per kg, table format').",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("last_scraped", models.DateTimeField(blank=True, null=True)),
                ("last_item_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="marketprice",
            name="source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prices",
                to="recipes.pricesource",
            ),
        ),
    ]
