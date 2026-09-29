from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0032_paymentpromise"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentpromise",
            name="promised_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
    ]
