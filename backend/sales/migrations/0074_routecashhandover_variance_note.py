from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0073_salesorder_stock_held"),
    ]

    operations = [
        migrations.AddField(
            model_name="routecashhandover",
            name="variance_note",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
