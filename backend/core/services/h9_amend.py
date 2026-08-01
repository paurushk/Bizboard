"""H9-A completed-document amend helpers (sales + purchases)."""

from decimal import Decimal

from core.exceptions import BusinessRuleError


def assert_h9a_line_allowlist(existing_items, items_data):
    """
    Only unit_price / discount_percent may change.
    Match by line id when present, else by product_id (order-independent).
    """
    existing = list(existing_items)
    if len(items_data) != len(existing):
        raise BusinessRuleError(
            "Completed document amend cannot add or remove lines (H9-A)."
        )

    by_id = {i.id: i for i in existing if getattr(i, "id", None) is not None}
    by_product: dict[int, list] = {}
    for i in existing:
        by_product.setdefault(i.product_id, []).append(i)

    used_ids: set[int] = set()
    for line in items_data:
        product = line["product"]
        product_id = product.pk if hasattr(product, "pk") else int(product)
        old = None
        line_id = line.get("id")
        if line_id is not None:
            try:
                line_id = int(line_id)
            except (TypeError, ValueError):
                line_id = None
        if line_id is not None and line_id in by_id and line_id not in used_ids:
            old = by_id[line_id]
            used_ids.add(line_id)
        else:
            bucket = by_product.get(product_id) or []
            while bucket:
                candidate = bucket.pop(0)
                if candidate.id in used_ids:
                    continue
                old = candidate
                used_ids.add(candidate.id)
                break
        if old is None:
            raise BusinessRuleError(
                "Completed document amend cannot change products (H9-A)."
            )
        if old.product_id != product_id:
            raise BusinessRuleError(
                "Completed document amend cannot change products (H9-A)."
            )
        if Decimal(str(line["quantity"])) != Decimal(str(old.quantity)):
            raise BusinessRuleError(
                "Completed document amend cannot change quantities (H9-A)."
            )
        if "gst_rate" in line and Decimal(str(line["gst_rate"])) != Decimal(str(old.gst_rate)):
            raise BusinessRuleError(
                "Completed document amend cannot change GST rates (H9-A)."
            )


def lines_prices_unchanged(existing_items, items_data) -> bool:
    """True when product/qty/gst/price/discount all match (order-independent)."""
    existing = list(existing_items)
    if len(items_data) != len(existing):
        return False
    by_product: dict[int, list] = {}
    for i in existing:
        by_product.setdefault(i.product_id, []).append(i)
    by_product = {k: list(v) for k, v in by_product.items()}
    for line in items_data:
        product = line["product"]
        product_id = product.pk if hasattr(product, "pk") else int(product)
        bucket = by_product.get(product_id) or []
        if not bucket:
            return False
        old = bucket.pop(0)
        if Decimal(str(line["quantity"])) != Decimal(str(old.quantity)):
            return False
        if Decimal(str(line.get("unit_price", old.unit_price))) != Decimal(str(old.unit_price)):
            return False
        if Decimal(str(line.get("discount_percent", old.discount_percent) or 0)) != Decimal(
            str(old.discount_percent or 0)
        ):
            return False
        if Decimal(str(line.get("gst_rate", old.gst_rate))) != Decimal(str(old.gst_rate)):
            return False
    return True


def existing_lines_as_items_data(items_qs):
    return [
        {
            "product": i.product,
            "description": i.description,
            "quantity": i.quantity,
            "unit_price": i.unit_price,
            "discount_percent": i.discount_percent,
            "gst_rate": i.gst_rate,
            "hsn_code": getattr(i, "hsn_code", "") or "",
            "mrp": getattr(i, "mrp", None),
            "unit_name": getattr(i, "unit_name", "") or "",
            "batch_no": getattr(i, "batch_no", "") or "",
            "exp_date": getattr(i, "exp_date", None),
            "mfg_date": getattr(i, "mfg_date", None),
        }
        for i in items_qs.select_related("product").all()
    ]
