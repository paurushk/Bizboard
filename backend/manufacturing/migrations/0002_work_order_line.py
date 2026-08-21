from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("manufacturing", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkOrderLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qty_per_unit", models.DecimalField(decimal_places=3, max_digits=12)),
                ("qty", models.DecimalField(decimal_places=3, max_digits=12)),
                (
                    "component",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="masters.product",
                    ),
                ),
                (
                    "work_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="component_lines",
                        to="manufacturing.workorder",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
    ]
