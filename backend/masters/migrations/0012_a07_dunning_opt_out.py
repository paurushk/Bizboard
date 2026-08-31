from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0011_a06_whatsapp_opt_in"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="dunning_opt_out",
            field=models.BooleanField(
                default=False,
                help_text="A-07: when True, skip automated AR reminders for this customer.",
            ),
        ),
    ]
