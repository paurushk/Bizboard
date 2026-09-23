"""COMP-002 replenishment quantity on the existing low-stock row."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from inventory.models import MovementType, StockMovement, Warehouse, WarehouseReorderLevel
from inventory.services import InventoryService, suggest_replenishment
from purchases.models import PurchaseOrder
from tests.conftest import make_product


def _enable(company):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_REPLENISHMENT"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


@pytest.mark.django_db
def test_unconfigured_falls_back_to_reorder_minus_available(tenant_a):
    product = make_product(tenant_a.company, sku="REP-1", reorder_level="10")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=warehouse, product=product,
        reorder_level=Decimal("10"), lead_time_days=0, safety_stock_qty=Decimal("0"),
    )
    since = timezone.localdate() - timedelta(days=14)
    suggestion = suggest_replenishment(
        tenant_a.company, warehouse, product,
        on_hand=Decimal("4"), reserved=Decimal("0"), reorder_level=Decimal("10"), since=since,
    )
    assert suggestion.suggested_qty == Decimal("6.000")
    assert suggestion.transfer_from_warehouse_id is None


@pytest.mark.django_db
def test_configured_uses_velocity_lead_time_and_safety(tenant_a):
    product = make_product(tenant_a.company, sku="REP-2", reorder_level="1")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=warehouse, product=product,
        reorder_level=Decimal("1"), lead_time_days=14, safety_stock_qty=Decimal("2"),
    )
    StockMovement.objects.create(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.SALE, quantity=Decimal("-14"), unit_cost=Decimal("10"),
        movement_date=timezone.localdate(),
    )
    since = timezone.localdate() - timedelta(days=14)
    suggestion = suggest_replenishment(
        tenant_a.company, warehouse, product,
        on_hand=Decimal("3"), reserved=Decimal("1"), reorder_level=Decimal("1"), since=since,
    )
    # available 2; velocity 14; per day 1; lead 14; safety 2 → 2+14-2 = 14
    assert suggestion.velocity_14d == Decimal("14")
    assert suggestion.suggested_qty == Decimal("14.000")


@pytest.mark.django_db
def test_zero_velocity_uses_safety_stock_only(tenant_a):
    product = make_product(tenant_a.company, sku="REP-3")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=warehouse, product=product,
        reorder_level=Decimal("0"), lead_time_days=7, safety_stock_qty=Decimal("4"),
    )
    since = timezone.localdate() - timedelta(days=14)
    suggestion = suggest_replenishment(
        tenant_a.company, warehouse, product,
        on_hand=Decimal("1"), reserved=Decimal("0"), reorder_level=Decimal("0"), since=since,
    )
    assert suggestion.velocity_14d == Decimal("0")
    assert suggestion.suggested_qty == Decimal("3.000")


@pytest.mark.django_db
def test_transfer_picks_largest_surplus_warehouse(tenant_a):
    product = make_product(tenant_a.company, sku="REP-4", reorder_level="5")
    home = InventoryService.default_warehouse(tenant_a.company)
    small = Warehouse.objects.create(company=tenant_a.company, name="Small", code="SM")
    large = Warehouse.objects.create(company=tenant_a.company, name="Large", code="LG")
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=small, product=product,
        movement_type=MovementType.PURCHASE, quantity="20", unit_cost="10", user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=large, product=product,
        movement_type=MovementType.PURCHASE, quantity="50", unit_cost="10", user=tenant_a.owner,
    )
    for wh, level in ((small, "5"), (large, "5"), (home, "10")):
        WarehouseReorderLevel.objects.create(
            company=tenant_a.company, warehouse=wh, product=product, reorder_level=Decimal(level),
        )
    since = timezone.localdate() - timedelta(days=14)
    suggestion = suggest_replenishment(
        tenant_a.company, home, product,
        on_hand=Decimal("1"), reserved=Decimal("0"), reorder_level=Decimal("10"), since=since,
    )
    assert suggestion.transfer_from_warehouse_id == large.id
    assert suggestion.transfer_from_warehouse_name == "Large"


@pytest.mark.django_db
def test_suggestion_does_not_create_a_purchase_order(tenant_a):
    from insights.alerts import build_business_alerts
    from tests.conftest import add_stock, create_draft_invoice, make_customer

    product = make_product(tenant_a.company, sku="REP-5", reorder_level="10")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    _enable(tenant_a.company)
    before = PurchaseOrder.objects.filter(company=tenant_a.company).count()
    alerts = [a for a in build_business_alerts(tenant_a.company) if a["code"] == "LOW_STOCK_FAST_MOVER"]
    assert alerts
    assert "suggested_qty" in alerts[0]["payload"]
    assert PurchaseOrder.objects.filter(company=tenant_a.company).count() == before
    assert "/purchases/orders/new?" in alerts[0]["cta_path"] or "/inventory/transfers?" in alerts[0]["cta_path"]


@pytest.mark.django_db
def test_flag_off_keeps_the_original_low_stock_row(tenant_a):
    from insights.alerts import build_business_alerts
    from tests.conftest import add_stock, create_draft_invoice, make_customer

    product = make_product(tenant_a.company, sku="REP-6", reorder_level="10", name="Fast soap")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    alerts = [a for a in build_business_alerts(tenant_a.company) if a["code"] == "LOW_STOCK_FAST_MOVER"]
    assert len(alerts) == 1
    assert alerts[0]["message"] == "Fast soap is below reorder and sold in the last 14 days."
    assert alerts[0]["cta_path"] == "/inventory/low-stock"
    assert "payload" not in alerts[0]


@pytest.mark.django_db
def test_end_to_end_zeroed_override_matches_pre_feature_trigger(tenant_a):
    """F1-002/#1 regression: through the real build_business_alerts() path (not a
    direct suggest_replenishment() call), a WarehouseReorderLevel row with
    lead_time_days=0/safety_stock_qty=0 must produce exactly reorder_level -
    available — the same number the pre-existing LOW_STOCK_FAST_MOVER alert's
    own trigger already computed, proving the "same trigger, same fallback
    qty" guarantee end-to-end.
    """
    from insights.alerts import build_business_alerts
    from tests.conftest import add_stock, create_draft_invoice, make_customer

    product = make_product(tenant_a.company, sku="REP-8", reorder_level="10", name="Zeroed override")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=warehouse, product=product,
        reorder_level=Decimal("10"), lead_time_days=0, safety_stock_qty=Decimal("0"),
    )
    add_stock(tenant_a, product, "12")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "10", "unit_price": "100"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    # available = 2, reorder_level = 10 -> pre-feature trigger fires (2 <= 10);
    # fallback formula must reproduce reorder_level - available = 8.
    _enable(tenant_a.company)
    alerts = [a for a in build_business_alerts(tenant_a.company) if a["code"] == "LOW_STOCK_FAST_MOVER"]
    assert len(alerts) == 1
    assert alerts[0]["payload"]["suggested_qty"] == "8.000"


@pytest.mark.django_db
def test_no_override_anywhere_skips_transfer_suggestion_for_aggregate_row(tenant_a):
    """Direct unit-level regression for F1-002: when `low_stock_alert_payload`
    marks a row as the company-wide aggregate (`is_warehouse_specific=False`,
    the no-override-anywhere case), `suggest_replenishment` must not compute a
    transfer suggestion against the arbitrary representative warehouse, even
    when a genuinely-surplus warehouse exists elsewhere for the same product.
    """
    product = make_product(tenant_a.company, sku="REP-10", reorder_level="10")
    home = InventoryService.default_warehouse(tenant_a.company)
    surplus_wh = Warehouse.objects.create(company=tenant_a.company, name="Surplus2", code="SURP2")
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=surplus_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity="100", unit_cost="10", user=tenant_a.owner,
    )
    since = timezone.localdate() - timedelta(days=14)
    suggestion = suggest_replenishment(
        tenant_a.company, home, product,
        on_hand=Decimal("2"), reserved=Decimal("0"), reorder_level=Decimal("10"), since=since,
        warehouse_specific=False,
    )
    assert suggestion.transfer_from_warehouse_id is None
    assert suggestion.transfer_from_warehouse_name is None
    # Purchase-fallback quantity is still computed correctly.
    assert suggestion.suggested_qty == Decimal("8.000")


@pytest.mark.django_db
def test_transfer_uses_each_candidates_own_reorder_level_not_the_current_warehouses(tenant_a):
    """Strengthens the largest-surplus test: the candidate warehouses' own
    reorder levels are set meaningfully different from the *current*
    warehouse's level, in a direction that would flip the winner if the code
    wrongly compared against `home`'s reorder level (10) instead of each
    candidate's own. `low_avail` has raw stock (12) that would look like
    +2 surplus against `home`'s level (10), but is *below* its own level (15)
    so must be excluded; `real_surplus` has less raw stock (8) but is above
    its own, much lower, level (3) so must win.
    """
    product = make_product(tenant_a.company, sku="REP-11", reorder_level="10")
    home = InventoryService.default_warehouse(tenant_a.company)
    low_avail = Warehouse.objects.create(company=tenant_a.company, name="LowAvail", code="LOWAV")
    real_surplus = Warehouse.objects.create(company=tenant_a.company, name="RealSurplus", code="REALSURP")
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=low_avail, product=product,
        movement_type=MovementType.PURCHASE, quantity="12", unit_cost="10", user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=real_surplus, product=product,
        movement_type=MovementType.PURCHASE, quantity="8", unit_cost="10", user=tenant_a.owner,
    )
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=home, product=product, reorder_level=Decimal("10"),
    )
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=low_avail, product=product, reorder_level=Decimal("15"),
    )
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=real_surplus, product=product, reorder_level=Decimal("3"),
    )
    since = timezone.localdate() - timedelta(days=14)
    suggestion = suggest_replenishment(
        tenant_a.company, home, product,
        on_hand=Decimal("1"), reserved=Decimal("0"), reorder_level=Decimal("10"), since=since,
    )
    assert suggestion.transfer_from_warehouse_id == real_surplus.id
    assert suggestion.transfer_from_warehouse_name == "RealSurplus"


@pytest.mark.django_db
def test_low_stock_query_count_does_not_grow_per_row(tenant_a):
    """F1-003 perf regression: suggest_replenishment must not issue a fresh
    WarehouseReorderLevel/StockBalance query per low-stock row once
    _low_stock() has precomputed the per-company maps.
    """
    from insights.alerts import build_business_alerts
    from tests.conftest import add_stock, create_draft_invoice, make_customer

    customer = make_customer(tenant_a.company)
    _enable(tenant_a.company)

    def _make_low_stock_product(sku):
        product = make_product(tenant_a.company, sku=sku, reorder_level="10")
        add_stock(tenant_a, product, "12")
        draft = create_draft_invoice(
            tenant_a, customer,
            [{"product": product.id, "quantity": "10", "unit_price": "100"}],
            invoice_type="NON_GST",
        )
        assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200

    _make_low_stock_product("REP-Q1")
    with CaptureQueriesContext(connection) as small:
        build_business_alerts(tenant_a.company)

    for i in range(5):
        _make_low_stock_product(f"REP-Q{i + 2}")
    with CaptureQueriesContext(connection) as large:
        alerts = build_business_alerts(tenant_a.company)

    assert len([a for a in alerts if a["code"] == "LOW_STOCK_FAST_MOVER"]) == 6
    # 5 extra low-stock products must not add anywhere near 5x4 extra queries —
    # allow a small constant per row for the parts that are still genuinely
    # per-row (the SALE-velocity aggregate), but the WarehouseReorderLevel/
    # StockBalance precompute itself must not scale with row count.
    assert len(large.captured_queries) - len(small.captured_queries) <= 5 * 3


@pytest.mark.django_db
def test_attention_row_says_purchase_when_there_is_no_surplus(tenant_a):
    from insights.alerts import build_business_alerts
    from insights.attention import _map_legacy_alerts
    from tests.conftest import add_stock, create_draft_invoice, make_customer

    product = make_product(tenant_a.company, sku="REP-7", reorder_level="10", name="Fast soap")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    _enable(tenant_a.company)
    raw = [a for a in build_business_alerts(tenant_a.company) if a["code"] == "LOW_STOCK_FAST_MOVER"]
    assert raw and raw[0]["payload"]["transfer_from_warehouse_id"] is None
    rows = [r for r in _map_legacy_alerts(tenant_a.company, timezone.localdate()) if r["code"] == "LOW_STOCK_FAST_MOVER"]
    assert rows[0]["action_label"] == "Purchase"
    assert rows[0]["action_href"].startswith("/purchases/orders/new?")


@pytest.mark.django_db
def test_purchase_plan_groups_documents_and_requires_replenishment(tenant_a):
    from core.exceptions import BusinessRuleError
    from inventory.planning import _documents, purchase_plan

    assert purchase_plan(tenant_a.company) is None
    flags = {"ENABLE_PURCHASE_PLANNING": True}
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    with pytest.raises(BusinessRuleError, match="replenishment"):
        purchase_plan(tenant_a.company)
    documents = _documents([
        {
            "product_id": 1,
            "suggested_qty": "2",
            "warehouse_id": 9,
            "supplier_id": 3,
            "transfer_from_warehouse_id": None,
        },
        {
            "product_id": 2,
            "suggested_qty": "1",
            "warehouse_id": 9,
            "supplier_id": 3,
            "transfer_from_warehouse_id": None,
        },
        {
            "product_id": 4,
            "suggested_qty": "5",
            "warehouse_id": 8,
            "supplier_id": None,
            "transfer_from_warehouse_id": 5,
        },
        {
            "product_id": 6,
            "suggested_qty": "3",
            "warehouse_id": 7,
            "supplier_id": None,
            "transfer_from_warehouse_id": 5,
        },
    ])
    purchase = next(doc for doc in documents if doc["kind"] == "purchase")
    transfers = [doc for doc in documents if doc["kind"] == "transfer"]
    assert purchase["supplier_id"] == 3
    assert len(purchase["lines"]) == 2
    assert {(doc["from_warehouse_id"], doc["to_warehouse_id"]) for doc in transfers} == {(5, 8), (5, 7)}
    assert all(len(doc["lines"]) == 1 for doc in transfers)
