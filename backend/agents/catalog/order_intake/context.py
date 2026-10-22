"""Order Intake: pasted text -> one SALES_ORDER_DRAFT proposal.

The text is untrusted. A model (or the rules parser) only turns it into {customer_hint, lines}; every id,
price and stock figure comes from the company's own data. A line the model returns must be copied from the
pasted text, and nothing the model says about price or discount is read.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation

from agents.error_codes import AGT_E_VALIDATION
from core.exceptions import BusinessRuleError

from . import resolver
from .parsing import MAX_LINES, normalize, parse_order

SALES_ORDER_DRAFT = "SALES_ORDER_DRAFT"


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _warn_unit(unit: str, product_unit: str) -> str:
    if unit and product_unit and unit.lower().rstrip("s") != product_unit.lower().rstrip("s"):
        return f"You wrote {unit}; this item is sold in {product_unit}. Check the quantity."
    return ""


def build_draft(tctx, parsed: dict, text: str) -> dict:
    from inventory.services import InventoryService
    from masters.models import Customer, Product

    company = tctx.company
    sha = _sha(text)
    customer = resolver.resolve_customer(company, parsed.get("customer_hint", ""), text)
    index = resolver.ProductIndex(company)

    lines, ignored = [], 0
    for item in (parsed.get("lines") or [])[:MAX_LINES]:
        hint = str(item.get("product_hint") or "").strip()
        res = index.resolve(hint)
        qty = item.get("qty")
        if qty is None and res["id"] is None and not res["alternatives"]:
            ignored += 1  # chatter such as a greeting
            continue
        warnings = []
        if qty is None:
            warnings.append("Quantity missing.")
        if res["id"] is None:
            warnings.append("Pick the product." if res["alternatives"] else "No matching product found.")
        lines.append({
            "raw": str(item.get("raw") or hint)[:300], "raw_norm": normalize(hint), "qty": qty,
            "unit": str(item.get("unit") or "")[:24], "product_id": res["id"], "product_name": res["name"],
            "match": res["match"], "alternatives": res["alternatives"], "warnings": warnings,
        })
    if not lines:
        raise BusinessRuleError("No order lines could be read from that text.", code=AGT_E_VALIDATION)

    # Facts that need the master rows: unit mismatch and stock, for the lines that matched.
    products = {p.pk: p for p in Product.objects.filter(company=company, pk__in=[l["product_id"] for l in lines if l["product_id"]]).select_related("unit")}
    for line in lines:
        product = products.get(line["product_id"])
        if product is None:
            continue
        note = _warn_unit(line["unit"], getattr(product.unit, "name", ""))
        if note:
            line["warnings"].append(note)
        if line["qty"] is not None and product.track_inventory and product.product_type == Product.ProductType.GOODS:
            available = InventoryService.available_quantity(company, product)
            if available < Decimal(line["qty"]):
                line["warnings"].append(f"Only {available.normalize():f} available in stock.")

    warnings = []
    if index.truncated:
        warnings.append(f"Your catalogue is larger than {resolver.MAX_CATALOGUE} items, so some products may not have been matched. Check each line.")
    if ignored:
        warnings.append(f"Ignored {ignored} line(s) with no quantity or product.")
    if customer["id"]:
        cust = Customer.objects.filter(company=company, pk=customer["id"]).first()
        if cust is not None and cust.status != Customer.Status.ACTIVE:
            warnings.append(f"This customer is {cust.status.lower()}; an order cannot be created until that changes.")
        elif cust is not None and cust.credit_limit and cust.credit_limit > 0:
            from payments.dunning import customer_risk_snapshot

            if Decimal(str(customer_risk_snapshot(company, cust)["outstanding"])) > cust.credit_limit:
                warnings.append("This customer is already over the credit limit.")
    else:
        warnings.append("Pick the customer.")

    evidence = [{"type": "fact", "id": "source", "label": f"Pasted order text, {len(lines)} line(s) read", "fact": sha[:8]}]
    if customer["id"]:
        evidence.append({"type": "customer", "id": customer["id"], "label": f"Customer: {customer['name']} ({customer['match']['source']})"})
    for line in lines:
        if line["product_id"]:
            evidence.append({"type": "product", "id": line["product_id"], "label": f"{line['raw_norm']} -> {line['product_name']} ({line['match']['source']})"})
    return {
        "kind": SALES_ORDER_DRAFT,
        "title": f"Order: {customer['name'] or parsed.get('customer_hint') or 'new customer'} ({len(lines)} line{'s' if len(lines) != 1 else ''})",
        "dedupe_key": f"ORDER:{sha[:20]}",
        "payload": {
            "customer_id": customer["id"], "customer_name": customer["name"],
            "customer_hint": str(parsed.get("customer_hint") or "")[:255], "customer_match": customer["match"],
            "customer_alternatives": customer["alternatives"], "lines": lines, "notes": "", "warnings": warnings,
        },
        "evidence": evidence[:40],
    }


# --- spec hooks --------------------------------------------------------------------------------
def build_context(tctx) -> dict:
    text = str((tctx.extras or {}).get("text") or "").strip()
    if not text:
        raise BusinessRuleError("There is no text to read.", code=AGT_E_VALIDATION)
    return {
        "facts": {"company_name": tctx.company.name, "text_sha": _sha(text)},
        "untrusted": {"order_text": text},
        "rules_only": False,
        "text": text,
    }


def rules_only(tctx, context) -> list[dict]:
    return [build_draft(tctx, parse_order(context["text"]), context["text"])]


def _number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("quantity must be a number")
    try:
        q = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("quantity must be a number") from None
    if not q.is_finite() or q <= 0 or q > Decimal("1000000"):
        raise ValueError("quantity out of range")
    return format(q.normalize(), "f")


def parse_final(tctx, context, reply: str) -> list[dict]:
    """Model JSON -> a draft. Any malformed or invented line raises ValueError (the rules parser then runs)."""
    data = json.loads(reply)
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list) or len(data["lines"]) > MAX_LINES:
        raise ValueError("lines must be a list")
    source = normalize(context["text"], None)  # the whole message: a line near the end must still be found
    lines = []
    for item in data["lines"]:
        if not isinstance(item, dict):
            raise ValueError("line must be an object")
        raw, hint = str(item.get("raw") or ""), str(item.get("product_hint") or "")
        if not hint.strip() or not raw.strip() or normalize(raw, None) not in source:
            raise ValueError("line is not from the pasted text")
        lines.append({"raw": raw, "qty": _number(item.get("qty")), "unit": str(item.get("unit") or "")[:24], "product_hint": hint})
    hint = str(data.get("customer_hint") or "")
    if hint and normalize(hint, None) not in source:
        hint = ""  # a buyer name the text does not contain is dropped, not trusted
    return [build_draft(tctx, {"customer_hint": hint, "lines": lines}, context["text"])]


def validate(tctx, context, drafts: list[dict]) -> None:
    from masters.models import Customer, Product

    for d in drafts:
        payload = d["payload"]
        cid = payload.get("customer_id")
        if cid and not Customer.objects.filter(company=tctx.company, pk=cid).exists():
            raise BusinessRuleError("Draft names a customer that is not in the books.", code=AGT_E_VALIDATION)
        ids = {l["product_id"] for l in payload["lines"] if l["product_id"]}
        if ids and Product.objects.filter(company=tctx.company, pk__in=ids).count() != len(ids):
            raise BusinessRuleError("Draft names a product that is not in the books.", code=AGT_E_VALIDATION)
        if not d["evidence"]:
            raise BusinessRuleError("Draft has no evidence.", code=AGT_E_VALIDATION)
