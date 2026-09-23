"""COMP-007 supplier price history — rows only, no score."""

from datetime import date
from decimal import Decimal

import pytest

from purchases.models import PurchaseInvoice, PurchaseItem, PurchaseOrder, PurchaseOrderItem
from tests.conftest import make_product, make_supplier


def _enable(company):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_SUPPLIER_PRICE_HISTORY"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _line(company, parent, product, price, *, order=False):
    kwargs = {
        "company": company,
        "product": product,
        "quantity": Decimal("2"),
        "unit_price": Decimal(price),
        "description": "item",
    }
    if order:
        return PurchaseOrderItem.objects.create(purchase_order=parent, **kwargs)
    return PurchaseItem.objects.create(invoice=parent, **kwargs)


@pytest.mark.django_db
def test_price_history_orders_invoice_and_po_without_a_score(tenant_a):
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    other = make_supplier(tenant_a.company, name="Other")
    product = make_product(tenant_a.company, sku="PH-1")
    older = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, number="PI-OLD",
        status=PurchaseInvoice.Status.COMPLETED, invoice_date=date(2026, 1, 1),
    )
    newer = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, number="PI-NEW",
        status=PurchaseInvoice.Status.COMPLETED, invoice_date=date(2026, 1, 3),
    )
    _line(tenant_a.company, older, product, "10")
    _line(tenant_a.company, newer, product, "14")
    order = PurchaseOrder.objects.create(
        company=tenant_a.company, supplier=supplier, number="PO-1",
        status=PurchaseOrder.Status.CONVERTED, order_date=date(2026, 1, 2),
    )
    _line(tenant_a.company, order, product, "12", order=True)
    draft = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, number="PI-DRAFT",
        status=PurchaseInvoice.Status.DRAFT, invoice_date=date(2026, 1, 3),
    )
    _line(tenant_a.company, draft, product, "99")
    stranger = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=other, number="PI-OTHER",
        status=PurchaseInvoice.Status.COMPLETED, invoice_date=date(2026, 1, 3),
    )
    _line(tenant_a.company, stranger, product, "1")

    resp = tenant_a.client.get(
        f"/api/v1/purchases/suppliers/{supplier.id}/price-history/",
        {"product": product.id},
    )
    assert resp.status_code == 200, resp.data
    body = resp.data
    blob = str(body).lower()
    for banned in ("score", "rank"):
        assert banned not in blob
    assert "lead_time_days" in body
    assert "fill_rate" in body
    assert body["over_receipt"] is False
    prices = [Decimal(str(row["unit_price"])) for row in body["rows"]]
    assert prices == [Decimal("10"), Decimal("12"), Decimal("14")]
    assert [row["source"] for row in body["rows"]] == [
        "PURCHASE_INVOICE", "PURCHASE_ORDER", "PURCHASE_INVOICE",
    ]


@pytest.mark.django_db
def test_cancelled_invoice_and_purchase_order_are_excluded(tenant_a):
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PH-3")
    cancelled_inv = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, number="PI-CANCELLED",
        status=PurchaseInvoice.Status.CANCELLED, invoice_date=date(2026, 1, 1),
    )
    _line(tenant_a.company, cancelled_inv, product, "77")
    cancelled_po = PurchaseOrder.objects.create(
        company=tenant_a.company, supplier=supplier, number="PO-CANCELLED",
        status=PurchaseOrder.Status.CANCELLED, order_date=date(2026, 1, 1),
    )
    _line(tenant_a.company, cancelled_po, product, "88", order=True)
    resp = tenant_a.client.get(
        f"/api/v1/purchases/suppliers/{supplier.id}/price-history/",
        {"product": product.id},
    )
    assert resp.status_code == 200
    assert resp.data["rows"] == []


@pytest.mark.django_db
def test_date_range_filters_both_invoice_and_order_rows(tenant_a):
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PH-4")
    early = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, number="PI-EARLY",
        status=PurchaseInvoice.Status.COMPLETED, invoice_date=date(2025, 1, 1),
    )
    _line(tenant_a.company, early, product, "5")
    late = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, number="PI-LATE",
        status=PurchaseInvoice.Status.COMPLETED, invoice_date=date(2026, 6, 1),
    )
    _line(tenant_a.company, late, product, "9")
    resp = tenant_a.client.get(
        f"/api/v1/purchases/suppliers/{supplier.id}/price-history/",
        {"product": product.id, "date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 200
    assert [Decimal(str(r["unit_price"])) for r in resp.data["rows"]] == [Decimal("9")]


@pytest.mark.django_db
def test_invalid_date_param_is_a_400(tenant_a):
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PH-4B")
    resp = tenant_a.client.get(
        f"/api/v1/purchases/suppliers/{supplier.id}/price-history/",
        {"product": product.id, "date_from": "not-a-date"},
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_result_set_is_capped_and_flags_truncation(tenant_a, monkeypatch):
    from purchases.views import SupplierPriceHistoryView

    monkeypatch.setattr(SupplierPriceHistoryView, "MAX_ROWS", 2)
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PH-5")
    for i, day in enumerate((1, 2, 3, 4), start=1):
        inv = PurchaseInvoice.objects.create(
            company=tenant_a.company, supplier=supplier, number=f"PI-CAP-{i}",
            status=PurchaseInvoice.Status.COMPLETED, invoice_date=date(2026, 1, day),
        )
        _line(tenant_a.company, inv, product, str(10 + i))
    resp = tenant_a.client.get(
        f"/api/v1/purchases/suppliers/{supplier.id}/price-history/",
        {"product": product.id},
    )
    assert resp.status_code == 200
    assert resp.data["total_count"] == 4
    assert resp.data["truncated"] is True
    assert len(resp.data["rows"]) == 2
    # kept rows are the most recent, still oldest-first within the kept window
    assert [Decimal(str(r["unit_price"])) for r in resp.data["rows"]] == [Decimal("13"), Decimal("14")]


@pytest.mark.django_db
def test_empty_history_and_flag_off(tenant_a, tenant_b):
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PH-2")
    empty = tenant_a.client.get(
        f"/api/v1/purchases/suppliers/{supplier.id}/price-history/",
        {"product": product.id},
    )
    assert empty.status_code == 200
    assert empty.data["rows"] == []
    hidden = tenant_b.client.get(
        f"/api/v1/purchases/suppliers/{supplier.id}/price-history/",
        {"product": product.id},
    )
    assert hidden.status_code == 404
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    off = tenant_a.client.get(
        f"/api/v1/purchases/suppliers/{supplier.id}/price-history/",
        {"product": product.id},
    )
    assert off.status_code == 404


@pytest.mark.django_db
def test_supply_metrics_report_lead_time_fill_rate_and_over_receipt(tenant_a):
    from purchases.models import GoodsReceipt, GoodsReceiptItem
    from purchases.reliability import supply_metrics

    supplier = make_supplier(tenant_a.company, name="Timed")
    product = make_product(tenant_a.company, sku="REL-1")
    order = PurchaseOrder.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        number="PO-REL",
        status=PurchaseOrder.Status.CONVERTED,
        order_date=date(2026, 1, 1),
    )
    PurchaseOrderItem.objects.create(
        company=tenant_a.company,
        purchase_order=order,
        product=product,
        quantity=Decimal("10"),
        unit_price=Decimal("5"),
        description="item",
    )
    cancelled = PurchaseOrder.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        number="PO-CAN",
        status=PurchaseOrder.Status.CANCELLED,
        order_date=date(2026, 1, 1),
    )
    PurchaseOrderItem.objects.create(
        company=tenant_a.company,
        purchase_order=cancelled,
        product=product,
        quantity=Decimal("100"),
        unit_price=Decimal("5"),
        description="cancelled",
    )
    receipt = GoodsReceipt.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        purchase_order=order,
        number="GRN-1",
        receipt_date=date(2026, 1, 5),
        status=GoodsReceipt.Status.COMPLETED,
    )
    GoodsReceiptItem.objects.create(
        company=tenant_a.company,
        goods_receipt=receipt,
        product=product,
        quantity_received=Decimal("12"),
        quantity_accepted=Decimal("12"),
    )
    metrics = supply_metrics(tenant_a.company, supplier, product)
    assert metrics["lead_time_days"] == "4.0"
    assert metrics["fill_rate"] == "1.0000"
    assert metrics["over_receipt"] is True
    assert "score" not in metrics
    assert "rank" not in metrics
