from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0018_plan_change_autopay")]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="proration_link_url",
            field=models.CharField(blank=True, default="", max_length=300),
        ),
        migrations.AddField(
            model_name="subscription",
            name="pending_authenticated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
