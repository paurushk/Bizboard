from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0011_review_void_utr"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierpayment",
            name="tds_section",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="supplierpayment",
            name="tds_rate",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name="supplierpayment",
            name="tds_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
