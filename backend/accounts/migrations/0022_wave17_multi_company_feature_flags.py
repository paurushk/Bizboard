# Wave 17G — multi-company: drop single active membership constraint; add active company + feature flags

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0021_wave16d_supply_gstin"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="companyuser",
            name="uniq_active_membership_per_user",
        ),
        migrations.AddField(
            model_name="user",
            name="active_company",
            field=models.ForeignKey(
                blank=True,
                help_text="Selected company for multi-membership users (Wave 17G).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="active_users",
                to="accounts.company",
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="feature_flags",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
