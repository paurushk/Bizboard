# BB-000017: denormalize company_id onto JournalLine

import django.db.models.deletion
from django.db import migrations, models


def backfill_journal_line_company(apps, schema_editor):
    JournalLine = apps.get_model("accounting", "JournalLine")
    for line in JournalLine.objects.select_related("entry").iterator(chunk_size=500):
        JournalLine.objects.filter(pk=line.pk).update(company_id=line.entry.company_id)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_wave4_tenancy_rbac_constraints"),
        ("accounting", "0002_wave3_posted_source_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="journalline",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.RunPython(backfill_journal_line_company, noop_reverse),
        migrations.AlterField(
            model_name="journalline",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(fields=["company", "account"], name="jl_company_account_idx"),
        ),
    ]
