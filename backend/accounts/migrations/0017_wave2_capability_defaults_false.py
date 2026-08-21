# BB-000227: can_create_* defaults False (least privilege for new memberships).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_payment_gateway_test_mode_default_false"),
    ]

    operations = [
        migrations.AlterField(
            model_name="companyuser",
            name="can_create_sales",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="companyuser",
            name="can_create_purchases",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="companyuser",
            name="can_create_payments",
            field=models.BooleanField(default=False),
        ),
    ]
