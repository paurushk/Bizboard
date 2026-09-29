from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0011_referral_reward_paid"),
    ]

    operations = [
        migrations.AlterField(
            model_name="opportunity",
            name="stage",
            field=models.CharField(
                choices=[
                    ("OPEN", "Open"),
                    ("QUALIFIED", "Qualified"),
                    ("NEGOTIATION", "Negotiation"),
                    ("WON", "Won"),
                    ("LOST", "Lost"),
                ],
                default="OPEN",
                max_length=16,
            ),
        ),
    ]
