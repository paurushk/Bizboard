from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0039_a06_whatsapp_send_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesitem",
            name="applied_price_list_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
