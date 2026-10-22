"""A small, believable manufacturing set-up for demos, training and the month simulation.

Builds, for one company: raw materials with stock, a finished good made from them with a by-product,
a semi-finished item inside a second recipe, work centres with a routing, an operator, a job worker,
an inspection checklist and a quality grade. Everything goes through the same services the screens use.
Safe to run twice: it looks for its own items by SKU first.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from accounting.services import seed_chart_of_accounts
from core.services.feature_flags import build_feature_flags
from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService
from manufacturing.models import Bom, BomLine, BomOutput, MfgSettings, Operator, WorkCentre
from manufacturing.services import bom as bom_svc
from manufacturing.services import shopfloor
from manufacturing.services.common import get_settings
from masters.models import Product, Supplier

SWITCHES = ("MFG_PLANNING", "MFG_QUALITY", "MFG_JOB_WORK", "MFG_SHOP_FLOOR", "MFG_COSTING_GL")


def _product(company, sku, name, *, price, sell="0", role="", batch=False):
    obj = Product.objects.filter(company=company, sku=sku).first()
    if obj:
        return obj
    return Product.objects.create(
        company=company, name=name, sku=sku, gst_rate=Decimal("18"), purchase_price=Decimal(price),
        selling_price=Decimal(sell), mfg_role=role, track_batch=batch,
    )


def build(company, user, *, switches: bool = True, stock: bool = True) -> dict:
    """Create or reuse the demo items. Returns the objects by short name."""
    if switches:
        flags = dict(company.feature_flags or {})
        flags.update({k: True for k in SWITCHES})
        # Manufacturing is a dark module: only the pack grant (or the plan) turns it on for a company.
        flags["manufacturing_pack_grant"] = True
        flags.pop("NAV_PACK_DEFAULT", None)         # a new company's pack sidebar hides Manufacturing
        company.feature_flags = flags
        company.accounting_enabled = True
        company.save(update_fields=["feature_flags", "accounting_enabled", "updated_at"])
        seed_chart_of_accounts(company, user)
        if hasattr(company, "_feature_flags_cache"):
            del company._feature_flags_cache
    cfg = get_settings(company)
    cfg.default_issue_mode = MfgSettings.IssueMode.SEPARATE
    cfg.save(update_fields=["default_issue_mode"])

    flour = _product(company, "DEMO-FLOUR", "Flour (kg)", price="30", role="RAW")
    sugar = _product(company, "DEMO-SUGAR", "Sugar (kg)", price="45", role="RAW")
    butter = _product(company, "DEMO-BUTTER", "Butter (kg)", price="500", role="RAW")
    box = _product(company, "DEMO-BOX", "Gift box", price="15", role="PACKING")
    dough = _product(company, "DEMO-DOUGH", "Dough (kg)", price="0", role="SEMI_FINISHED")
    biscuit = _product(company, "DEMO-BISCUIT", "Butter biscuits (pack)", price="0", sell="120", role="FINISHED", batch=True)
    crumbs = _product(company, "DEMO-CRUMBS", "Biscuit crumbs (kg)", price="0", sell="20", role="BY_PRODUCT")

    if stock:
        for prod, qty, cost in ((flour, 500, "30"), (sugar, 200, "45"), (butter, 80, "500"), (box, 400, "15")):
            if not StockMovement.objects.filter(company=company, product=prod).exists():
                InventoryService.post_movement(
                    company=company, product=prod, movement_type=MovementType.OPENING_STOCK,
                    quantity=Decimal(qty), unit_cost=Decimal(cost), user=user,
                )

    def recipe(product, name, lines, outputs=()):
        existing = Bom.objects.filter(company=company, product=product, status="ACTIVE").first()
        if existing:
            return existing
        bom = Bom.objects.create(
            company=company, product=product, name=name, status="DRAFT", revision_no=bom_svc.next_revision_no(company, product),
            output_qty=Decimal("10"), yield_pct=Decimal("100"), created_by=user, updated_by=user,
        )
        for comp, q, *flags in lines:
            BomLine.objects.create(
                bom=bom, company=company, component=comp, qty=Decimal(q), scrap_pct=Decimal("1"),
                is_phantom=bool(flags and flags[0] == "phantom"),
            )
        for out_product, kind, q in outputs:
            BomOutput.objects.create(bom=bom, company=company, product=out_product, kind=kind, qty=Decimal(q))
        return bom_svc.activate_revision(bom, user)

    dough_bom = recipe(dough, "Dough", [(flour, "6"), (sugar, "2"), (butter, "2")])
    biscuit_bom = recipe(
        biscuit, "Butter biscuits", [(dough, "5", "phantom"), (box, "10")], outputs=[(crumbs, "BY_PRODUCT", "0.2")],
    )

    centre = WorkCentre.objects.filter(company=company, code="OVEN").first() or WorkCentre.objects.create(
        company=company, code="OVEN", name="Oven line", hours_per_day=Decimal("8"), labour_rate=Decimal("180"),
        machine_rate=Decimal("120"), overhead_rate=Decimal("40"), created_by=user, updated_by=user,
    )
    if not biscuit_bom.operations.exists() and not biscuit_bom.is_locked:
        shopfloor.set_routing(
            biscuit_bom, [{"work_centre": centre, "name": "Mix and bake", "setup_minutes": "10", "run_minutes_per_unit": "1.5"}], user,
        )
    if not Operator.objects.filter(company=company, code="DEMO1").exists():
        shopfloor.create_operator(company, user, code="DEMO1", name="Demo operator", pin="2468")
    supplier = Supplier.objects.filter(company=company, name="Demo Packers (job worker)").first() or Supplier.objects.create(
        company=company, name="Demo Packers (job worker)", state=company.state or "Karnataka", gstin="",
    )
    return {
        "flour": flour, "sugar": sugar, "butter": butter, "box": box, "dough": dough, "biscuit": biscuit,
        "crumbs": crumbs, "dough_bom": dough_bom, "biscuit_bom": biscuit_bom, "centre": centre, "job_worker": supplier,
        "today": timezone.localdate(), "flags": build_feature_flags(company=company),
    }
