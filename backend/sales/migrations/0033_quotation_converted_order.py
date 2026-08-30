from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0032_item_godown_expiry"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="converted_order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="source_quotations",
                to="sales.salesorder",
            ),
        ),
    ]
