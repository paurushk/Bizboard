from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0031_stock_count_line_versions")]

    operations = [
        migrations.AddField(
            model_name="stocktransfer", name="dispatched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stocktransferline", name="shortage_resolution",
            field=models.CharField(blank=True, max_length=16),
        ),
    ]
