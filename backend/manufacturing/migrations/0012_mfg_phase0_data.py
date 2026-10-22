"""MFG-01 / MFG-02 / MFG-03 data backfill. Idempotent; safe to run twice.

* Numbers BOM revisions per product and marks one ACTIVE default (closes B8-018) before the
  unique constraints arrive in 0013.
* Locks BOMs that a work order already used.
* Gives every existing work order a number, a product, a cost summary and an issue mode.
* DEF-2: serials a work order used up were marked SCRAPPED. Move the ones we can prove
  came from a RELEASED or COMPLETED work order to CONSUMED. Anything else stays as it is.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations
from django.db.models import F
from django.utils import timezone

TWO = Decimal("0.01")


def _q2(value):
    return Decimal(value or 0).quantize(TWO, rounding=ROUND_HALF_UP)


def number_bom_revisions(apps, schema_editor):
    Bom = apps.get_model("manufacturing", "Bom")
    WorkOrder = apps.get_model("manufacturing", "WorkOrder")
    used_bom_ids = set(
        WorkOrder.objects.exclude(bom__isnull=True).values_list("bom_id", flat=True).distinct()
    )
    by_product = {}
    for bom in Bom.objects.order_by("company_id", "product_id", "created_at", "id"):
        by_product.setdefault((bom.company_id, bom.product_id), []).append(bom)
    now = timezone.now()
    for boms in by_product.values():
        active = [b for b in boms if b.status == "ACTIVE"]
        # The newest ACTIVE revision is the default; the others stay ACTIVE but not default.
        default_id = active[-1].pk if active else None
        for number, bom in enumerate(boms, start=1):
            bom.revision_no = number
            bom.is_default = bom.pk == default_id
            bom.parent_revision_id = boms[number - 2].pk if number > 1 else None
            if bom.pk in used_bom_ids and bom.locked_at is None:
                bom.locked_at = now
            bom.save(update_fields=["revision_no", "is_default", "parent_revision", "locked_at"])


def backfill_work_orders(apps, schema_editor):
    WorkOrder = apps.get_model("manufacturing", "WorkOrder")
    WorkOrderLine = apps.get_model("manufacturing", "WorkOrderLine")
    StockMovement = apps.get_model("inventory", "StockMovement")
    for wo in WorkOrder.objects.select_related("bom").order_by("id"):
        fields = []
        if wo.product_id is None and wo.bom_id:
            wo.product_id = wo.bom.product_id
            fields.append("product")
        if not wo.number:
            wo.number = f"WO-{wo.pk}"
            fields.append("number")
        # Every work order that already exists issued all its materials at release.
        wo.issue_mode = "AUTO_AT_RELEASE"
        fields.append("issue_mode")
        issued = Decimal("0")
        if wo.status in ("RELEASED", "COMPLETED"):
            for move in StockMovement.objects.filter(
                company_id=wo.company_id,
                reference_type="work_order",
                reference_id=str(wo.pk),
                movement_type="MANUFACTURE_ISSUE",
            ):
                issued += Decimal(move.unit_cost or 0) * abs(Decimal(move.quantity))
        wo.cost_issued = _q2(issued)
        fields.append("cost_issued")
        if wo.status == "COMPLETED":
            wo.cost_received = _q2(issued)
            wo.qty_completed = wo.qty
            fields.extend(["cost_received", "qty_completed"])
        if wo.status in ("RELEASED", "COMPLETED"):
            WorkOrderLine.objects.filter(work_order_id=wo.pk).update(qty_issued=F("qty"))
        wo.save(update_fields=fields)


def consumed_serials(apps, schema_editor):
    WorkOrder = apps.get_model("manufacturing", "WorkOrder")
    WorkOrderLine = apps.get_model("manufacturing", "WorkOrderLine")
    SerialNumber = apps.get_model("inventory", "SerialNumber")
    TraceLink = apps.get_model("inventory", "TraceLink")
    converted = 0
    for line in WorkOrderLine.objects.filter(
        work_order__status__in=["RELEASED", "COMPLETED"],
    ).exclude(serial_numbers=[]).select_related("work_order"):
        wo = line.work_order
        numbers = [str(n).strip() for n in (line.serial_numbers or []) if str(n).strip()]
        if not numbers:
            continue
        rows = SerialNumber.objects.filter(
            company_id=wo.company_id, product_id=line.component_id,
            serial_number__in=numbers, status="SCRAPPED",
        )
        for serial in rows:
            serial.status = "CONSUMED"
            serial.save(update_fields=["status"])
            converted += 1
            if not TraceLink.objects.filter(
                company_id=wo.company_id, work_order_id=wo.pk,
                input_product_id=line.component_id, input_serial=serial.serial_number,
            ).exists():
                TraceLink.objects.create(
                    company_id=wo.company_id,
                    work_order_id=wo.pk,
                    document_type="work_order",
                    document_id=wo.pk,
                    input_product_id=line.component_id,
                    input_serial=serial.serial_number,
                    output_product_id=wo.product_id,
                    output_batch_id=wo.batch_id if wo.status == "COMPLETED" else None,
                    qty=Decimal("1"),
                )
    if converted:
        print(f"  mfg 0012: {converted} serial(s) SCRAPPED -> CONSUMED")


def forwards(apps, schema_editor):
    number_bom_revisions(apps, schema_editor)
    backfill_work_orders(apps, schema_editor)
    consumed_serials(apps, schema_editor)


def backwards(apps, schema_editor):
    # Revision numbers, defaults and caches are derived data; nothing to undo. Serials
    # go back to SCRAPPED only for the rows that have a work-order trace link.
    SerialNumber = apps.get_model("inventory", "SerialNumber")
    TraceLink = apps.get_model("inventory", "TraceLink")
    for link in TraceLink.objects.filter(document_type="work_order").exclude(input_serial=""):
        SerialNumber.objects.filter(
            company_id=link.company_id, product_id=link.input_product_id,
            serial_number=link.input_serial, status="CONSUMED",
        ).update(status="SCRAPPED")


class Migration(migrations.Migration):
    dependencies = [
        ("manufacturing", "0011_mfg_phase0"),
        ("inventory", "0033_mfg_phase0"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
