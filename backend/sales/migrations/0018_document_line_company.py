# Denormalize company onto sales document line items (BB-000017 / next-batch-8).

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def _backfill_company(apps, schema_editor):
    pairs = [
        ("SalesItem", "SalesInvoice", "invoice"),
        ("QuotationItem", "Quotation", "quotation"),
        ("SalesReturnItem", "SalesReturn", "sales_return"),
        ("SalesCreditNoteItem", "SalesCreditNote", "credit_note"),
        ("SalesDebitNoteItem", "SalesDebitNote", "debit_note"),
        ("SalesOrderItem", "SalesOrder", "sales_order"),
        ("DeliveryChallanItem", "DeliveryChallan", "challan"),
    ]
    for item_name, parent_name, fk in pairs:
        Item = apps.get_model("sales", item_name)
        Parent = apps.get_model("sales", parent_name)
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
        ("sales", "0017_so_confirmed_reservation_challan_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="deliverychallanitem",
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
            model_name="quotationitem",
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
            model_name="salescreditnoteitem",
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
            model_name="salesdebitnoteitem",
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
            model_name="salesitem",
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
            model_name="salesorderitem",
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
            model_name="salesreturnitem",
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
            model_name="deliverychallanitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="quotationitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="salescreditnoteitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="salesdebitnoteitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="salesitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="salesorderitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="salesreturnitem",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
    ]
