from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0058_usermfa"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="session_version",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
