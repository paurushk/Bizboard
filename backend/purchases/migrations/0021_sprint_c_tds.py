from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0020_note_rcm_cess"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoice",
            name="tds_section",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="purchaseinvoice",
            name="tds_rate",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name="purchaseinvoice",
            name="tds_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
