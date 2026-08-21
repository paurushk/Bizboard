# Generated manually for Wave 3 books/GST integrity

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0015_wave2_uniqueness_and_allocations"),
    ]

    operations = [
        migrations.AddField(
            model_name="salescreditnote",
            name="sales_return",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="credit_notes",
                to="sales.salesreturn",
            ),
        ),
    ]
