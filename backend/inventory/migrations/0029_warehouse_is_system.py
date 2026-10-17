from django.db import migrations, models


def mark_in_transit(apps, schema_editor):
    Warehouse = apps.get_model("inventory", "Warehouse")
    Warehouse.objects.filter(code="IN_TRANSIT").update(is_system=True)


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0028_stockcountline_skipped_drift"),
    ]

    operations = [
        migrations.AddField(
            model_name="warehouse",
            name="is_system",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_in_transit, migrations.RunPython.noop),
    ]
