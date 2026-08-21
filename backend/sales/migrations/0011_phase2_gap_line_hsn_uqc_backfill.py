# Backfill blank HSN/UQC snapshots on sales invoice and CN/DN lines from product/unit.

from django.db import migrations


def _backfill(apps, schema_editor):
    from core.services.uqc import resolve_uqc_code

    Product = apps.get_model("masters", "Product")
    Unit = apps.get_model("masters", "Unit")
    products = {
        p.pk: p
        for p in Product.objects.select_related("unit").all()
    }
    units = {u.pk: u for u in Unit.objects.all()}

    def fill_lines(model):
        for item in model.objects.all().iterator(chunk_size=500):
            changed = []
            product = products.get(item.product_id)
            if product is None:
                continue
            unit = units.get(product.unit_id) if getattr(product, "unit_id", None) else None
            if not (getattr(item, "hsn_code", None) or "").strip():
                hsn = (getattr(product, "hsn_code", None) or "").strip()
                if hsn:
                    item.hsn_code = hsn
                    changed.append("hsn_code")
            if not (getattr(item, "uqc_code", None) or "").strip():
                uqc = resolve_uqc_code(unit=unit, unit_name=getattr(item, "unit_name", None))
                if uqc:
                    item.uqc_code = uqc
                    changed.append("uqc_code")
            if not (getattr(item, "unit_name", None) or "").strip() and unit is not None:
                name = (unit.short_name or unit.name or "").upper()[:16]
                if name:
                    item.unit_name = name
                    changed.append("unit_name")
            if changed:
                item.save(update_fields=changed)

    SalesItem = apps.get_model("sales", "SalesItem")
    SalesCreditNoteItem = apps.get_model("sales", "SalesCreditNoteItem")
    SalesDebitNoteItem = apps.get_model("sales", "SalesDebitNoteItem")
    for model in (SalesItem, SalesCreditNoteItem, SalesDebitNoteItem):
        fill_lines(model)


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0010_phase2_gap_inclusive_price"),
        ("masters", "0003_phase2_gst_returns_readiness"),
    ]

    operations = [
        migrations.RunPython(_backfill, _noop),
    ]
