# Generated manually for Wave 1 OTP hash storage.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_phase3_payments_cash_ops"),
    ]

    operations = [
        migrations.AlterField(
            model_name="otpchallenge",
            name="code",
            field=models.CharField(max_length=128),
        ),
    ]
