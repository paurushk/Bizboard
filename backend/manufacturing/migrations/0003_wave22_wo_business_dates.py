from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("manufacturing", "0002_work_order_line"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="released_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workorder",
            name="completed_at",
            field=models.DateField(blank=True, null=True),
        ),
    ]
