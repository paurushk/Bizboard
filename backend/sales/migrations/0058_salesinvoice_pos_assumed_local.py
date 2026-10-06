from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0057_roadmap_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="pos_assumed_local",
            field=models.BooleanField(default=False),
        ),
    ]
