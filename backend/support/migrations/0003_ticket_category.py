from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("support", "0002_roadmap_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="category",
            field=models.CharField(
                choices=[("GENERAL", "General"), ("NUMBER_MISMATCH", "Number Mismatch")],
                db_index=True,
                default="GENERAL",
                max_length=32,
            ),
        ),
    ]
