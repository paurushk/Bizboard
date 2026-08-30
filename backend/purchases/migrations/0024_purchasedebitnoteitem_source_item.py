from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0023_purchasereturnitem_condition"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasedebitnoteitem",
            name="source_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="debit_note_items",
                to="purchases.purchaseitem",
            ),
        ),
    ]
