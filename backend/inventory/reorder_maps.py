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


def open_order_quantities(company, product_ids, *, now=None):
    """Quantity already on its way from suppliers, per product: ``(counted, stale)``.

    Shared by Purchase planning and the Demand forecast so neither orders what the other has
    already ordered (INV-IDR-08). Counted: draft purchase orders raised in the last
    ``PLANNING_DRAFT_PO_DAYS`` days, and orders converted into a purchase bill that is not yet
    completed (the goods have not been received). Draft orders older than that are forgotten
    drafts: they are returned as ``stale`` so the screen can say so, but they are not counted.
    """
    from datetime import timedelta

    from django.db.models import Sum
    from django.utils import timezone

    from inventory import planning_settings as ps
    from purchases.models import PurchaseInvoice, PurchaseOrder, PurchaseOrderItem

    counted: dict[int, object] = {}
    stale: dict[int, object] = {}
    if not product_ids:
        return counted, stale
    cutoff = (now or timezone.now()) - timedelta(days=ps.number_setting(company, ps.PLANNING_DRAFT_PO_DAYS))
    base = PurchaseOrderItem.objects.filter(company=company, product_id__in=list(product_ids))
    fresh = base.filter(purchase_order__status=PurchaseOrder.Status.DRAFT, purchase_order__created_at__gte=cutoff)
    old = base.filter(purchase_order__status=PurchaseOrder.Status.DRAFT, purchase_order__created_at__lt=cutoff)
    converted = base.filter(
        purchase_order__status=PurchaseOrder.Status.CONVERTED,
        purchase_order__converted_purchase__status=PurchaseInvoice.Status.DRAFT,
    )
    for queryset, target in ((fresh, counted), (converted, counted), (old, stale)):
        for row in queryset.values("product_id").annotate(qty=Sum("quantity")).order_by():
            target[row["product_id"]] = target.get(row["product_id"], 0) + (row["qty"] or 0)
    return counted, stale


def last_purchase_prices(company, product_ids) -> dict[int, object]:
    """The unit price on the latest completed purchase bill, per product (one grouped read).

    ``Product.purchase_price`` is the price typed into the item master, which can be years old.
    """
    from purchases.models import PurchaseInvoice, PurchaseItem

    if not product_ids:
        return {}
    rows = (
        PurchaseItem.objects.filter(
            company=company, product_id__in=list(product_ids), invoice__status=PurchaseInvoice.Status.COMPLETED,
        )
        .order_by("-invoice__invoice_date", "-invoice_id", "-id")
        .values_list("product_id", "unit_price")
    )
    found: dict[int, object] = {}
    for product_id, price in rows:
        found.setdefault(product_id, price)
    return found
