# UniqueConstraint on GstReturnSnapshot (company, return_type, period, content_hash)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0001_phase2_gst_returns_readiness"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="gstreturnsnapshot",
            constraint=models.UniqueConstraint(
                fields=("company", "return_type", "period", "content_hash"),
                name="uniq_gst_return_snapshot_content",
            ),
        ),
    ]
