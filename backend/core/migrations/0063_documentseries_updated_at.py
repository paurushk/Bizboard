import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0062_rls_care_jobs_tables")]

    operations = [
        migrations.AddField(
            model_name="documentseries",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
