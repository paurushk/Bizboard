import re

from django.db import migrations, models


def backfill_walk_in(apps, schema_editor):
    Customer = apps.get_model("masters", "Customer")
    pattern = re.compile(r"walk[\s-]?in", re.I)
    company_ids = (
        Customer.objects.filter(is_deleted=False)
        .values_list("company_id", flat=True)
        .distinct()
    )
    for company_id in company_ids:
        matches = [
            row
            for row in Customer.objects.filter(company_id=company_id, is_deleted=False)
            if pattern.search(row.name or "")
        ]
        if len(matches) == 1:
            row = matches[0]
            row.is_pos_walk_in = True
            row.save(update_fields=["is_pos_walk_in"])


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0030_soft_delete_aware_uniques"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="is_pos_walk_in",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_pos_walk_in=True, is_deleted=False),
                fields=("company",),
                name="uniq_pos_walk_in_per_company",
            ),
        ),
        migrations.RunPython(backfill_walk_in, migrations.RunPython.noop),
    ]
