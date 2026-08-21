from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0004_wave2_uniqueness_and_allocations"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="bankaccount",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_default=True),
                fields=("company",),
                name="one_default_bank_account_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="bankstatementline",
            constraint=models.UniqueConstraint(
                condition=~models.Q(line_hash=""),
                fields=("company", "statement", "line_hash"),
                name="uniq_bank_statement_line_hash",
            ),
        ),
    ]
