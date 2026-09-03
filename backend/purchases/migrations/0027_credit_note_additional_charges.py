from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0026_b06_hsn_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasecreditnote",
            name="additional_charges",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
