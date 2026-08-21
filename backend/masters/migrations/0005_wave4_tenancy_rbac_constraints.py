# BB-000017: denormalize company_id onto PriceListItem

import django.db.models.deletion
from django.db import migrations, models


def backfill_price_list_item_company(apps, schema_editor):
    PriceListItem = apps.get_model("masters", "PriceListItem")
    for item in PriceListItem.objects.select_related("price_list").iterator(chunk_size=500):
        PriceListItem.objects.filter(pk=item.pk).update(company_id=item.price_list.company_id)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_wave4_tenancy_rbac_constraints"),
        ("masters", "0004_product_track_batch_product_track_serial_pricelist_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pricelistitem",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.RunPython(backfill_price_list_item_company, noop_reverse),
        migrations.AlterField(
            model_name="pricelistitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="customer",
            name="status",
            field=models.CharField(
                choices=[("ACTIVE", "Active"), ("BLOCKED", "Blocked"), ("INACTIVE", "Inactive")],
                default="ACTIVE",
                max_length=8,
            ),
        ),
    ]
