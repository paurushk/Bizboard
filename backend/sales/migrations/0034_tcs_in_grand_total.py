from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0033_quotation_converted_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="tcs_in_grand_total",
            field=models.BooleanField(default=False),
        ),
    ]
