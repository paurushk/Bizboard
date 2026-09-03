"""H9-A completed-document amend helpers (sales + purchases)."""

from decimal import Decimal

from core.exceptions import BusinessRuleError


def _pair_amend_lines(existing_items, items_data):
    """H9-02: the single source of truth for pairing amended payload lines to
    existing rows — by line id when present, else FIFO by product_id. Both
    ``assert_h9a_line_allowlist`` and ``lines_prices_unchanged`` use this so
    they can never disagree on which old row a line maps to.

    Returns ``[(line, old_item_or_None), ...]`` in payload order.
    """
    existing = list(existing_items)
    by_id = {i.id: i for i in existing if getattr(i, "id", None) is not None}
    by_product: dict[int, list] = {}
    for i in existing:
        by_product.setdefault(i.product_id, []).append(i)

    used_ids: set[int] = set()
    pairs = []
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
        pairs.append((line, old))
    return pairs


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

    for line, old in _pair_amend_lines(existing, items_data):
        product = line["product"]
        product_id = product.pk if hasattr(product, "pk") else int(product)
        if old is None:
            raise BusinessRuleError(
                "Completed document amend cannot change products (H9-A)."
            )
        if old.product_id != product_id:
            raise BusinessRuleError(
                "Completed document amend cannot change products (H9-A)."
            )
        if "description" in line and (line.get("description") or "") != (getattr(old, "description", "") or ""):
            raise BusinessRuleError(
                "Completed document amend cannot change description (H9-A)."
            )
        if Decimal(str(line["quantity"])) != Decimal(str(old.quantity)):
            raise BusinessRuleError(
                "Completed document amend cannot change quantities (H9-A)."
            )
        if "gst_rate" in line and Decimal(str(line["gst_rate"])) != Decimal(str(old.gst_rate)):
            raise BusinessRuleError(
                "Completed document amend cannot change GST rates (H9-A)."
            )
        if "supply_nature" in line:
            old_nature = (getattr(old, "supply_nature", None) or "").strip()
            new_nature = (line.get("supply_nature") or "").strip()
            if new_nature != old_nature:
                raise BusinessRuleError(
                    "Completed document amend cannot change supply nature (H9-A)."
                )
        if "cess_rate" in line and Decimal(str(line["cess_rate"] or 0)) != Decimal(
            str(getattr(old, "cess_rate", 0) or 0)
        ):
            raise BusinessRuleError(
                "Completed document amend cannot change cess rates (H9-A)."
            )
        if "cess_amount" in line and Decimal(str(line["cess_amount"] or 0)) != Decimal(
            str(getattr(old, "cess_amount", 0) or 0)
        ):
            raise BusinessRuleError(
                "Completed document amend cannot change cess amounts (H9-A)."
            )
        if "hsn_code" in line and (line.get("hsn_code") or "") != (getattr(old, "hsn_code", "") or ""):
            raise BusinessRuleError(
                "Completed document amend cannot change HSN (H9-A)."
            )
        if "serial_numbers" in line:
            old_sns = list(getattr(old, "serial_numbers", None) or [])
            new_sns = list(line.get("serial_numbers") or [])
            if old_sns != new_sns:
                raise BusinessRuleError(
                    "Completed document amend cannot change serial numbers (H9-A)."
                )
        if "batch_no" in line and (line.get("batch_no") or "") != (getattr(old, "batch_no", "") or ""):
            raise BusinessRuleError(
                "Completed document amend cannot change batch (H9-A)."
            )
        # H9-01: for INCLUSIVE price-mode documents `unit_price_inclusive` is what
        # actually drives taxable_amount / tax (see
        # billing.extract_exclusive_from_inclusive_line). Allowing it through the
        # H9-A gate would let a post-Complete amend re-rate a filed invoice.
        if "unit_price_inclusive" in line:
            _old_incl = getattr(old, "unit_price_inclusive", None)
            if _old_incl is not None and Decimal(str(line.get("unit_price_inclusive") or 0)) != Decimal(
                str(_old_incl or 0)
            ):
                raise BusinessRuleError(
                    "Completed document amend cannot change the tax-inclusive unit price (H9-A). "
                    "Adjust the exclusive unit price / discount instead."
                )
        for _frozen_attr, _label in (
            ("mrp", "MRP"),
            ("exp_date", "expiry date"),
            ("mfg_date", "manufacture date"),
            ("uqc_code", "unit (UQC)"),
        ):
            if _frozen_attr in line:
                _old_v = getattr(old, _frozen_attr, None)
                _new_v = line.get(_frozen_attr)
                if _old_v is not None and str(_new_v or "") != str(_old_v or ""):
                    raise BusinessRuleError(
                        f"Completed document amend cannot change {_label} (H9-A)."
                    )


def lines_prices_unchanged(existing_items, items_data) -> bool:
    """True when product/qty/gst/price/discount all match (order-independent).

    H9-02: uses the same id-first pairing as ``assert_h9a_line_allowlist`` so
    two same-product lines can't make the two helpers disagree.
    """
    existing = list(existing_items)
    if len(items_data) != len(existing):
        return False
    for line, old in _pair_amend_lines(existing, items_data):
        product = line["product"]
        product_id = product.pk if hasattr(product, "pk") else int(product)
        if old is None or old.product_id != product_id:
            return False
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
        if Decimal(str(line.get("cess_rate", getattr(old, "cess_rate", 0) or 0) or 0)) != Decimal(
            str(getattr(old, "cess_rate", 0) or 0)
        ):
            return False
        if Decimal(str(line.get("cess_amount", getattr(old, "cess_amount", 0) or 0) or 0)) != Decimal(
            str(getattr(old, "cess_amount", 0) or 0)
        ):
            return False
        old_nature = getattr(old, "supply_nature", None) or ""
        if str(line.get("supply_nature", old_nature) or "") != str(old_nature):
            return False
        old_incl = getattr(old, "unit_price_inclusive", None)
        if "unit_price_inclusive" in line or old_incl is not None:
            new_incl = line.get("unit_price_inclusive", old_incl)
            if Decimal(str(new_incl or 0)) != Decimal(str(old_incl or 0)):
                return False
    return True


def existing_lines_as_items_data(items_qs):
    return [
        {
            "id": i.id,
            "product": i.product,
            "description": i.description,
            "quantity": i.quantity,
            "unit_price": i.unit_price,
            "discount_percent": i.discount_percent,
            "gst_rate": i.gst_rate,
            "cess_rate": getattr(i, "cess_rate", 0) or 0,
            "hsn_code": getattr(i, "hsn_code", "") or "",
            "mrp": getattr(i, "mrp", None),
            "unit_name": getattr(i, "unit_name", "") or "",
            "uqc_code": getattr(i, "uqc_code", "") or "",
            "unit_price_inclusive": getattr(i, "unit_price_inclusive", None),
            "serial_numbers": list(getattr(i, "serial_numbers", None) or []),
            "supply_nature": getattr(i, "supply_nature", "") or "",
            "rate_override": getattr(i, "rate_override", False),
            "cess_amount": getattr(i, "cess_amount", None),
            "batch_no": getattr(i, "batch_no", "") or "",
            "exp_date": getattr(i, "exp_date", None),
            "mfg_date": getattr(i, "mfg_date", None),
        }
        for i in items_qs.select_related("product").all()
    ]
