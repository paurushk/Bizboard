import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0056_whatsapp_webhook_token"),
        ("contracts", "0002_growth_os"),
        ("masters", "0021_customer_coordinates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("contract", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="covered_products", to="contracts.contract")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contract_coverages", to="masters.product")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="contractproduct",
            index=models.Index(fields=["company", "contract"], name="contract_product_co_idx"),
        ),
        migrations.AddConstraint(
            model_name="contractproduct",
            constraint=models.UniqueConstraint(fields=("contract", "product"), name="uniq_contract_product"),
        ),
    ]
