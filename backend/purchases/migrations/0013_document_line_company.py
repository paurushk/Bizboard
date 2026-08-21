# Denormalize company onto purchase document line items (BB-000017 / next-batch-8).

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def _backfill_company(apps, schema_editor):
    pairs = [
        ("PurchaseItem", "PurchaseInvoice", "invoice"),
        ("PurchaseReturnItem", "PurchaseReturn", "purchase_return"),
        ("PurchaseCreditNoteItem", "PurchaseCreditNote", "credit_note"),
        ("PurchaseDebitNoteItem", "PurchaseDebitNote", "debit_note"),
        ("PurchaseOrderItem", "PurchaseOrder", "purchase_order"),
    ]
    for item_name, parent_name, fk in pairs:
        Item = apps.get_model("purchases", item_name)
        Parent = apps.get_model("purchases", parent_name)
        Item.objects.filter(company_id__isnull=True).update(
            company_id=Subquery(
                Parent.objects.filter(pk=OuterRef(f"{fk}_id")).values("company_id")[:1]
            )
        )


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_document_line_company"),
        ("purchases", "0012_wave2_uniqueness_and_allocations"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasecreditnoteitem",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AddField(
            model_name="purchasedebitnoteitem",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AddField(
            model_name="purchaseitem",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AddField(
            model_name="purchaseorderitem",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AddField(
            model_name="purchasereturnitem",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.RunPython(_backfill_company, _noop),
        migrations.AlterField(
            model_name="purchasecreditnoteitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="purchasedebitnoteitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="purchaseitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="purchaseorderitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="purchasereturnitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
    ]
