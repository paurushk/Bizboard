# Generated manually for Wave 17D

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0021_wave16d_supply_gstin"),
        ("inventory", "0005_wave16_gl_fifo_gstr2b"),
        ("masters", "0005_wave4_tenancy_rbac_constraints"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Bom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200)),
                ("status", models.CharField(
                    choices=[("DRAFT", "Draft"), ("ACTIVE", "Active"), ("ARCHIVED", "Archived")],
                    default="DRAFT", max_length=16,
                )),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="boms_as_fg", to="masters.product")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"], "verbose_name": "BOM", "verbose_name_plural": "BOMs"},
        ),
        migrations.CreateModel(
            name="WorkOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("qty", models.DecimalField(decimal_places=3, max_digits=12)),
                ("status", models.CharField(
                    choices=[("DRAFT", "Draft"), ("RELEASED", "Released"), ("COMPLETED", "Completed")],
                    default="DRAFT", max_length=16,
                )),
                ("bom", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="work_orders", to="manufacturing.bom")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("warehouse", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="BomLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qty", models.DecimalField(decimal_places=3, max_digits=12)),
                ("bom", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="manufacturing.bom")),
                ("component", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bom_lines_as_component", to="masters.product")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
