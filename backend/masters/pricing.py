"""Server-side price list resolution (BB-000657)."""

from decimal import Decimal

from masters.models import PriceListItem


def resolve_unit_price(*, customer, product, requested_price=None, role: str | None = None) -> Decimal:
    """Return the unit price that must be stored on the document line.

    Staff/API callers cannot undercut a price-list item. OWNER may override.
    """
    fallback = product.selling_price
    if requested_price is not None and str(requested_price) != "":
        requested = Decimal(str(requested_price))
    else:
        requested = None

    price_list_id = getattr(customer, "price_list_id", None) if customer is not None else None
    if not price_list_id:
        return requested if requested is not None else Decimal(str(fallback or 0))

    item = (
        PriceListItem.objects.filter(price_list_id=price_list_id, product=product)
        .only("unit_price")
        .first()
    )
    if item is None:
        return requested if requested is not None else Decimal(str(fallback or 0))

    list_price = Decimal(str(item.unit_price))
    if requested is None:
        return list_price
    if requested != list_price and (role or "").upper() == "OWNER":
        return requested
    return list_price
