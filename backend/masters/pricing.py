"""Server-side price list resolution (BB-000657 / C-04 qty slabs)."""

from decimal import Decimal

from masters.models import PriceListItem


def _qty(value) -> Decimal:
    if value is None or str(value) == "":
        return Decimal("1")
    q = Decimal(str(value))
    return q if q > 0 else Decimal("1")


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
    if requested != list_price and (role or "").upper() == "OWNER":
        return requested
    return list_price
