"""Per-company reorder and stock maps shared by alerts and purchase planning."""

from __future__ import annotations


def reorder_and_balances(company, product_ids):
    from inventory.models import StockBalance, WarehouseReorderLevel

    reorder_row_by_key = {}
    levels_by_product: dict = {}
    balances_by_product: dict = {}
    if not product_ids:
        return reorder_row_by_key, levels_by_product, balances_by_product
    for level_row in WarehouseReorderLevel.objects.filter(company=company, product_id__in=product_ids):
        reorder_row_by_key[(level_row.warehouse_id, level_row.product_id)] = level_row
        levels_by_product.setdefault(level_row.product_id, {})[level_row.warehouse_id] = level_row
    for bal_row in (
        StockBalance.objects.filter(company=company, product_id__in=product_ids).select_related("warehouse")
    ):
        balances_by_product.setdefault(bal_row.product_id, []).append(bal_row)
    return reorder_row_by_key, levels_by_product, balances_by_product


def last_completed_suppliers(company, product_ids) -> dict[int, int]:
    """One grouped read: latest completed purchase invoice supplier per product."""
    from purchases.models import PurchaseInvoice

    if not product_ids:
        return {}
    rows = (
        PurchaseInvoice.objects.filter(
            company=company,
            supplier__isnull=False,
            status=PurchaseInvoice.Status.COMPLETED,
            items__product_id__in=product_ids,
        )
        .order_by("-invoice_date", "-id")
        .values_list("items__product_id", "supplier_id")
    )
    found: dict[int, int] = {}
    for product_id, supplier_id in rows:
        if product_id not in found and supplier_id is not None:
            found[product_id] = supplier_id
    return found
