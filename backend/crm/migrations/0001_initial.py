# Generated manually for Wave 17D

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0021_wave16d_supply_gstin"),
        ("masters", "0005_wave4_tenancy_rbac_constraints"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200)),
                ("phone", models.CharField(blank=True, max_length=20)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("status", models.CharField(
                    choices=[
                        ("NEW", "New"), ("CONTACTED", "Contacted"),
                        ("QUALIFIED", "Qualified"), ("LOST", "Lost"),
                    ],
                    default="NEW", max_length=16,
                )),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leads", to="masters.customer")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Opportunity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("stage", models.CharField(
                    choices=[("OPEN", "Open"), ("WON", "Won"), ("LOST", "Lost")],
                    default="OPEN", max_length=16,
                )),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="opportunities", to="masters.customer")),
                ("lead", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="opportunities", to="crm.lead")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "verbose_name_plural": "opportunities"},
        ),
    ]
