from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0064_statutory_licence_lock")]

    operations = [
        migrations.AddField(
            model_name="company",
            name="scheduled_backup_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
