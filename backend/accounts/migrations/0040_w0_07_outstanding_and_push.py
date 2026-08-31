from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0039_w0_02_recompute_tax_on_complete"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="outstanding_basis",
            field=models.CharField(
                choices=[
                    ("GL_WHEN_BOOKS", "Gl When Books"),
                    ("DOCUMENTS_ALWAYS", "Documents Always"),
                ],
                default="GL_WHEN_BOOKS",
                help_text=(
                    "W0-07 / PD-02: GL_WHEN_BOOKS uses AR 1200 net of advances 2300 when "
                    "accounting_enabled. DOCUMENTS_ALWAYS keeps the document-derived figure."
                ),
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="push_token",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]
