from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0010_b06_hsn_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="whatsapp_opt_in",
            field=models.BooleanField(
                default=False,
                help_text="A-06: Cloud WhatsApp only when True. wa.me open-in-app is always allowed.",
            ),
        ),
    ]
