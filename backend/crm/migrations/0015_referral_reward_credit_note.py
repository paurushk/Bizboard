from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0057_roadmap_items"),
        ("crm", "0014_leadactivity_due_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralreward",
            name="credit_note",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="referral_rewards",
                to="sales.salescreditnote",
            ),
        ),
    ]
