from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_sprint1_idempotency_record"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentseries",
            name="gstin_key",
            field=models.CharField(blank=True, default="", max_length=15),
        ),
        migrations.AddField(
            model_name="documentseries",
            name="fy_label",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AlterUniqueTogether(
            name="documentseries",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="documentseries",
            constraint=models.UniqueConstraint(
                fields=("company", "doc_type", "gstin_key", "fy_label"),
                name="uniq_document_series_gstin_fy",
            ),
        ),
    ]
