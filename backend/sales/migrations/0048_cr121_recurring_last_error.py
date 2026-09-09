from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0047_b2_026_recurring_header_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="recurringinvoiceschedule",
            name="last_error",
            field=models.TextField(blank=True, default=""),
        ),
    ]
