from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0021_transfer_transit_and_reservations"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockcountsession",
            name="blind",
            field=models.BooleanField(
                default=False,
                help_text="When set, counter responses omit the expected quantity until review.",
            ),
        ),
    ]
