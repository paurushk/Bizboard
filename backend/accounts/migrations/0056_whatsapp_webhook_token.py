import secrets

from django.db import migrations, models


def backfill_whatsapp_tokens(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    for company in Company.objects.all().iterator():
        if company.whatsapp_webhook_token:
            continue
        company.whatsapp_webhook_token = secrets.token_urlsafe(24)
        company.save(update_fields=["whatsapp_webhook_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0055_os_vision_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="whatsapp_webhook_token",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.RunPython(backfill_whatsapp_tokens, migrations.RunPython.noop),
    ]
