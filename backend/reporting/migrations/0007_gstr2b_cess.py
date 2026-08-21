from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0006_sprint2_2b_itc_unreviewed"),
    ]

    operations = [
        migrations.AddField(
            model_name="gstr2bingest",
            name="cess",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
    ]
