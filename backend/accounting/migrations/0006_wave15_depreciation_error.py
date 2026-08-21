# BB-000490: surface failed depreciation on BooksHealth.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0005_wave13_journal_number_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="fixedasset",
            name="last_depreciation_error",
            field=models.TextField(blank=True, default=""),
        ),
    ]
