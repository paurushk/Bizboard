from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_fileasset_pdf_kinds"),
        ("planwave", "0004_open_quarantine_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="pharmacydispense",
            name="prescription_image",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="core.fileasset",
            ),
        ),
    ]
