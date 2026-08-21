from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0005_wave18_cess_itc"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gstr2bingest",
            name="itc_eligibility",
            field=models.CharField(
                choices=[
                    ("UNREVIEWED", "UNREVIEWED"),
                    ("CLAIMABLE", "CLAIMABLE"),
                    ("INELIGIBLE", "INELIGIBLE"),
                    ("REVERSED", "REVERSED"),
                ],
                default="UNREVIEWED",
                max_length=12,
            ),
        ),
    ]
