from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0041_c02_challan_lot"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="tcs_amount_manual",
            field=models.BooleanField(default=False),
        ),
    ]
