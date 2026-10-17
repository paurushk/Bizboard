from django.db import migrations, models


def mark_existing_holders(apps, schema_editor):
    """Orders already confirmed or partly processed are the ones that hold a reservation today."""
    SalesOrder = apps.get_model("sales", "SalesOrder")
    SalesOrder.objects.filter(status__in=("CONFIRMED", "PARTIALLY_CONVERTED")).update(stock_held=True)


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0072_bill_import_review_v2"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesorder",
            name="stock_held",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_holders, migrations.RunPython.noop),
    ]
