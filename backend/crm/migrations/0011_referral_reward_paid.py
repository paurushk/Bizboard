from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0010_opportunity_competitor"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralreward",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="referralreward",
            name="reward_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("PAID", "Paid"),
                ],
                default="PENDING",
                max_length=16,
            ),
        ),
    ]
