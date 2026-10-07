from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0013_cash_shift_and_depreciation_catchup"),
    ]

    operations = [
        migrations.AddField(
            model_name="cashshiftregister",
            name="cash_dropped",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
