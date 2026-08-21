# Wave 3: allow re-post after reverse (H9 amend GL repost)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="journalentry",
            name="uniq_accounting_source_posting",
        ),
        migrations.AddConstraint(
            model_name="journalentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(source_id__isnull=False, status="POSTED"),
                fields=("company", "source_type", "source_id", "purpose"),
                name="uniq_accounting_source_posting",
            ),
        ),
    ]
