from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0029_warehouse_is_system"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockmovement",
            name="reason_code",
            field=models.CharField(blank=True, db_index=True, default="", max_length=24),
        ),
    ]
