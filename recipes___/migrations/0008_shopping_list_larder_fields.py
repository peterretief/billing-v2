from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0007_price_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoppinglistitem",
            name="quantity_in_larder",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="shoppinglistitem",
            name="quantity_to_buy",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="shoppinglistitem",
            name="larder_value",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10,
                help_text="Cost-equivalent of the quantity already stocked in the larder.",
            ),
        ),
        migrations.AlterField(
            model_name="shoppinglistitem",
            name="estimated_cost",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10,
                help_text="Cost to purchase the shortfall (total minus larder stock).",
            ),
        ),
    ]
