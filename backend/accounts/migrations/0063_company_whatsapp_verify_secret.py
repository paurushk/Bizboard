from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0062_company_expense_gl_start_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="whatsapp_verify_token",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="company",
            name="whatsapp_app_secret",
            field=models.TextField(blank=True, default=""),
        ),
    ]
