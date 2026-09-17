# SQLite AddField stores telegram_chat_id as NOT NULL with no column default, so
# INSERTs that omit the column (restore, raw SQL, some factories) raise IntegrityError.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0051_telegram_notifications"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="telegram_chat_id",
            field=models.CharField(
                blank=True, db_default="", db_index=True, default="", max_length=64
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="telegram_link_code",
            field=models.CharField(blank=True, db_default="", default="", max_length=32),
        ),
    ]
