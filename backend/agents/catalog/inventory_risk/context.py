"""Inventory Risk Agent: turns the Purchase planning rows into transfer and purchase drafts.

Every quantity comes from ``inventory.planning.purchase_plan`` (which uses ``suggest_replenishment``); this module
only groups them into documents and makes transfers lot-aware. A split shortage (part moved, part bought) becomes
a transfer draft and a purchase draft that share a ``group_key`` and are approved separately. No model is used.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from agents.error_codes import AGT_E_VALIDATION
from core.exceptions import BusinessRuleError

TRANSFER, PURCHASE, NEEDS_SUPPLIER = "STOCK_TRANSFER", "PURCHASE_REQUEST", "PURCHASE_NEEDS_SUPPLIER"
_KEY = re.compile(r"^LOW_STOCK_FAST_MOVER:(?:product:)?(\d+)$")
MAX_EVIDENCE = 40


def product_from_ref(ref: str) -> int | None:
    m = _KEY.match((ref or "").strip())
    return int(m.group(1)) if m else None


def _num(value) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _lots(company, product, warehouse, qty: Decimal) -> tuple[list[dict], Decimal]:
    """Split ``qty`` over the donor godown's usable lots, earliest expiry first. Returns (lines, qty covered).

    ``fefo_batches`` already drops expired lots (when the company blocks them) and lots quality has not released,
    so those are never suggested."""
    from inventory.models import StockBalance
    from inventory.services import InventoryValuationService

    lines, left = [], qty
    for lot in InventoryValuationService.fefo_batches(company, product, warehouse=warehouse):
        if left <= 0:
            break
        bal = StockBalance.objects.filter(company=company, warehouse=warehouse, product=product, batch=lot).first()
        have = (bal.on_hand - bal.reserved) if bal else Decimal("0")
        take = min(have, left)
        if take > 0:
            lines.append({"batch_id": lot.pk, "batch_no": lot.batch_no, "qty": take})
            left -= take
    return lines, qty - left


def build_context(tctx) -> dict:
    from inventory.models import Warehouse
    from inventory.planning import purchase_plan
    from masters.models import Product

    company = tctx.company
    only = product_from_ref(tctx.run.trigger_ref)
    plan = purchase_plan(company) or {"rows": []}
    rows = [r for r in plan["rows"] if only is None or r["product_id"] == only]
    kinds = dict(Warehouse.objects.filter(company=company).values_list("id", "kind"))
    donors = {w.pk: w for w in Warehouse.objects.filter(company=company)}
    products = {p.pk: p for p in Product.objects.filter(company=company, pk__in={r["product_id"] for r in rows}).select_related("unit")}

    transfers, purchases, skipped, no_supplier = defaultdict(list), defaultdict(list), [], []
    for r in rows:
        product = products.get(r["product_id"])
        if product is None:
            continue
        qty = Decimal(r["suggested_qty"])
        base = {
            "item": r["product_name"], "unit": r["unit"], "product_id": r["product_id"],
            "warehouse_id": r["warehouse_id"], "warehouse_name": r["warehouse_name"],
            "_note": f"{r['available']} available, reorder at {r['reorder_level']}"
                     + (f", about {r['days_to_stockout']} days left" if r["days_to_stockout"] is not None else ""),
        }
        if r["transfer_from_warehouse_id"]:
            src = r["transfer_from_warehouse_id"]
            if kinds.get(src) != "NORMAL" or kinds.get(r["warehouse_id"]) != "NORMAL":
                skipped.append({"product": r["product_name"], "reason": "donor or destination is not a normal godown"})
                continue
            donor = donors[src]
            if product.track_batch:
                lots, covered = _lots(company, product, donor, qty)
                for lot in lots:
                    transfers[(src, r["transfer_from_warehouse_name"], r["warehouse_id"], r["warehouse_name"])].append(
                        {**base, "qty": lot["qty"], "batch_id": lot["batch_id"], "batch_no": lot["batch_no"]})
                if covered < qty:
                    skipped.append({"product": r["product_name"], "reason": f"only {_num(covered)} of {_num(qty)} is in usable lots"})
            else:
                transfers[(src, r["transfer_from_warehouse_name"], r["warehouse_id"], r["warehouse_name"])].append(
                    {**base, "qty": qty, "batch_id": None, "batch_no": ""})
        elif r["supplier_id"]:
            purchases[(r["supplier_id"], r["supplier_name"])].append({**base, "qty": qty, "batch_id": None, "batch_no": ""})
        else:
            skipped.append({"product": r["product_name"], "reason": "no supplier on record"})
            no_supplier.append({**base, "qty": qty, "batch_id": None, "batch_no": ""})
    return {
        "facts": {"company_name": company.name, "scoped_product": only, "rows": rows, "skipped": skipped},
        "rules_only": True,
        "transfers": dict(transfers),
        "purchases": dict(purchases),
        "no_supplier": no_supplier,
    }


def _line(l: dict) -> dict:
    return {
        "item": l["item"], "qty": _num(l["qty"]), "unit": l["unit"], "note": l["_note"], "product_id": l["product_id"],
        "batch_id": l["batch_id"], "batch_no": l["batch_no"], "warehouse_id": l["warehouse_id"], "warehouse_name": l["warehouse_name"],
    }


def _evidence(lines: list[dict]) -> list[dict]:
    seen, out = set(), []
    for l in lines:
        if l["product_id"] in seen:
            continue
        seen.add(l["product_id"])
        out.append({"type": "product", "id": l["product_id"], "label": f"{l['item']}: {l['_note']}", "fact": _num(l["qty"])})
    return out[:MAX_EVIDENCE]


def _group(tctx, scoped, dest_id) -> str:
    return tctx.run.trigger_ref if scoped else f"INV:{dest_id}:{tctx.as_of.isoformat()}"


MAX_LINES = 100  # the payload limit; a longer list becomes several drafts of the same kind


def _chunks(lines: list[dict]) -> list[list[dict]]:
    return [lines[i:i + MAX_LINES] for i in range(0, len(lines), MAX_LINES)] or [[]]


def _part_title(part: int) -> str:
    return f", part {part + 1}" if part else ""


def _part_key(part: int) -> str:
    return f":c{part}" if part else ""


def rules_only(tctx, context) -> list[dict]:
    scoped = context["facts"]["scoped_product"]
    suffix = f":P{scoped}" if scoped else ""
    drafts = []
    for (src, src_name, dst, dst_name), all_lines in sorted(context["transfers"].items()):
        for part, lines in enumerate(_chunks(all_lines)):
            drafts.append({
                "kind": TRANSFER,
                "title": f"Move stock: {src_name} to {dst_name} ({len({l['product_id'] for l in lines})} item(s))" + _part_title(part),
                "dedupe_key": f"TRANSFER:{src}:{dst}{suffix}{_part_key(part)}",
                "group_key": _group(tctx, scoped, dst),
                "payload": {
                    "from_warehouse_id": src, "from_warehouse_name": src_name, "to_warehouse_id": dst, "to_warehouse_name": dst_name,
                    "lines": [_line(l) for l in lines],
                },
                "evidence": _evidence(lines),
            })
    for (sup, sup_name), all_lines in sorted(context["purchases"].items()):
        dst = all_lines[0]["warehouse_id"]
        for part, lines in enumerate(_chunks(all_lines)):
            drafts.append({
                "kind": PURCHASE,
                "title": f"Reorder from {sup_name} ({len({l['product_id'] for l in lines})} item(s))" + _part_title(part),
                "dedupe_key": f"PURCHASE:{sup}{suffix}{_part_key(part)}",
                "group_key": _group(tctx, scoped, dst),
                "payload": {"supplier_id": sup, "supplier_name": sup_name, "lines": [_line(l) for l in lines]},
                "evidence": _evidence(lines),
            })
    gap = context.get("no_supplier") or []
    for part, lines in enumerate(_chunks(gap) if gap else []):
        drafts.append({
            "kind": NEEDS_SUPPLIER,
            "title": f"{len(lines)} low item(s) have no supplier on record" + _part_title(part),
            "dedupe_key": f"NOSUPPLIER{suffix}{_part_key(part)}",
            "group_key": _group(tctx, scoped, lines[0]["warehouse_id"]),
            "payload": {"lines": [_line(l) for l in lines]},
            "evidence": _evidence(lines),
        })
    if not drafts and scoped:
        raise BusinessRuleError("Nothing needs moving or ordering right now.", code=AGT_E_VALIDATION)
    return drafts


def parse_final(tctx, context, text: str) -> list[dict]:
    raise ValueError("this agent does not use a model")


def validate(tctx, context, drafts: list[dict]) -> None:
    from inventory.models import Warehouse
    from masters.models import Product

    for d in drafts:
        if not d["evidence"]:
            raise BusinessRuleError("Draft has no evidence.", code=AGT_E_VALIDATION)
        ids = {l["product_id"] for l in d["payload"]["lines"]}
        if Product.objects.filter(company=tctx.company, pk__in=ids).count() != len(ids):
            raise BusinessRuleError("Draft names an item that is not in the books.", code=AGT_E_VALIDATION)
        if d["kind"] == TRANSFER:
            wh = {d["payload"]["from_warehouse_id"], d["payload"]["to_warehouse_id"]}
            if len(wh) != 2 or Warehouse.objects.filter(company=tctx.company, pk__in=wh).count() != 2:
                raise BusinessRuleError("Draft names a godown that is not in the books.", code=AGT_E_VALIDATION)
