"""Server-side price list resolution (BB-000657 / C-04 qty slabs)."""

from decimal import Decimal

from core.exceptions import BusinessRuleError
from masters.models import PriceListItem


def _qty(value) -> Decimal:
    if value is None or str(value) == "":
        return Decimal("1")
    q = Decimal(str(value))
    return q if q > 0 else Decimal("1")


def _range_hi(max_qty):
    if max_qty is None or str(max_qty) == "":
        return None
    return Decimal(str(max_qty))


def ranges_overlap(min_a, max_a, min_b, max_b) -> bool:
    lo_a = Decimal(str(min_a or 1))
    lo_b = Decimal(str(min_b or 1))
    hi_a = _range_hi(max_a)
    hi_b = _range_hi(max_b)
    if hi_a is not None and hi_a < lo_b:
        return False
    if hi_b is not None and hi_b < lo_a:
        return False
    return True


def assert_slab_bounds(min_qty, max_qty) -> None:
    min_q = Decimal(str(min_qty or 1))
    hi = _range_hi(max_qty)
    if hi is not None and hi < min_q:
        raise BusinessRuleError("max_qty cannot be less than min_qty.")


def assert_slab_payloads(items) -> None:
    """Reject max<min and overlapping qty ranges for the same product in a payload."""
    by_product: dict = {}
    for item in items or []:
        product = item.get("product") if isinstance(item, dict) else getattr(item, "product", None)
        product_id = product.pk if hasattr(product, "pk") else int(product)
        min_q = item.get("min_qty") if isinstance(item, dict) else getattr(item, "min_qty", 1)
        max_q = item.get("max_qty") if isinstance(item, dict) else getattr(item, "max_qty", None)
        assert_slab_bounds(min_q, max_q)
        others = by_product.setdefault(product_id, [])
        for o_min, o_max in others:
            if ranges_overlap(min_q, max_q, o_min, o_max):
                raise BusinessRuleError(
                    "Quantity slabs for this product overlap on the same price list."
                )
        others.append((min_q, max_q))


def _matching_slab(*, price_list_id, product, quantity: Decimal):
    items = list(
        PriceListItem.objects.filter(price_list_id=price_list_id, product=product)
        .select_related("price_list")
        .order_by("-min_qty")
    )
    for item in items:
        min_q = Decimal(str(item.min_qty or 1))
        max_q = item.max_qty
        if quantity < min_q:
            continue
        if max_q is not None and quantity > Decimal(str(max_q)):
            continue
        return item
    return None


def resolve_party_price(*, customer, product, quantity=None) -> tuple[Decimal | None, str]:
    """Return (list unit price, list name) or (None, "") if no party list/slab."""
    fallback = None
    price_list_id = getattr(customer, "price_list_id", None) if customer is not None else None
    if not price_list_id:
        return fallback, ""
    item = _matching_slab(price_list_id=price_list_id, product=product, quantity=_qty(quantity))
    if item is None:
        return fallback, ""
    price = Decimal(str(item.unit_price))
    disc = Decimal(str(item.discount_pct or 0))
    if disc:
        price = (price * (Decimal("100") - disc) / Decimal("100")).quantize(Decimal("0.01"))
    name = getattr(getattr(item, "price_list", None), "name", "") or ""
    if not name:
        name = getattr(customer.price_list, "name", "") if getattr(customer, "price_list", None) else ""
    return price, name


def resolve_unit_price(
    *,
    customer,
    product,
    requested_price=None,
    role: str | None = None,
    quantity=None,
) -> Decimal:
    """Return the unit price that must be stored on the document line.

    Staff/API callers cannot undercut a price-list slab. OWNER may override.
    """
    fallback = Decimal(str(product.selling_price or 0))
    if requested_price is not None and str(requested_price) != "":
        requested = Decimal(str(requested_price))
    else:
        requested = None

    list_price, _name = resolve_party_price(customer=customer, product=product, quantity=quantity)
    if list_price is None:
        return requested if requested is not None else fallback

    if requested is None:
        return list_price
    # B8-031: the guard is meant to stop *undercutting* a slab. Pricing *above*
    # the list (a negotiated higher rate) is legitimate for any role — only
    # clamp when the request is below the slab and the caller isn't an OWNER.
    if requested >= list_price:
        return requested
    if (role or "").upper() == "OWNER":
        return requested
    return list_price
