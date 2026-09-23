from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from insights.attention import ATTENTION_ROW_KEYS, build_attention_rows, snooze_attention_row
from insights.models import AttentionRowState
from reporting.models import Gstr2bIngest
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product


def _complete_non_gst(tenant, customer, product, qty="1", price="100"):
    draft = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": qty, "unit_price": price}],
        invoice_type="NON_GST",
    )
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return SalesInvoice.objects.get(pk=draft["id"])


@pytest.mark.django_db
def test_attention_ranked_overdue_itc_dead_stock(tenant_a):
    customer = make_customer(tenant_a.company)
    sold = make_product(tenant_a.company, sku="ATT-SOLD", purchase_price="80", selling_price="100")
    dead = make_product(tenant_a.company, sku="ATT-DEAD", purchase_price="50", selling_price="90", reorder_level="0")
    add_stock(tenant_a, sold, "20", unit_cost="80")
    add_stock(tenant_a, dead, "40", unit_cost="50")

    inv = _complete_non_gst(tenant_a, customer, sold, price="120")
    past = timezone.localdate() - timedelta(days=100)
    SalesInvoice.objects.filter(pk=inv.pk).update(invoice_date=past, due_date=past)

    period = timezone.localdate().strftime("%Y-%m")
    Gstr2bIngest.objects.create(
        company=tenant_a.company,
        period=period,
        supplier_gstin="29AAAAA0000A1Z5",
        invoice_number="P-1",
        taxable_value=Decimal("10000"),
        cgst=Decimal("900"),
        sgst=Decimal("900"),
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
    )

    cu = tenant_a.company.memberships.get(user=tenant_a.owner)
    rows = build_attention_rows(tenant_a.company, company_user=cu)
    codes = {r["code"] for r in rows}
    assert "ITC_AT_RISK" in codes
    assert "DEAD_STOCK" in codes
    overdue_like = codes & {
        "AR_OVERDUE_CRITICAL",
        "AR_OVERDUE_CUSTOMER",
        "AR_COLLECTION_RISK",
        "OVERDUE_CONCENTRATION",
    }
    assert overdue_like

    by_code = {r["code"]: r for r in rows}
    for row in rows:
        assert list(row.keys()) == list(ATTENTION_ROW_KEYS)
        assert row["currency"] == "INR"
        assert isinstance(row["money_impact_paise"], int)
        assert "entity_ref" in row and "type" in row["entity_ref"] and "id" in row["entity_ref"]

    itc = by_code["ITC_AT_RISK"]
    assert itc["money_impact_paise"] == 180000  # 900+900 GST
    assert itc["action_href"] == "/reports/gstr2b"
    assert itc["source_ticket"] == "B-03"

    dead_row = by_code["DEAD_STOCK"]
    assert dead_row["money_impact_paise"] > 0
    assert dead_row["action_href"] == "/inventory/stock"

    # Rank: critical ITC before info dead stock.
    assert [r["code"] for r in rows].index("ITC_AT_RISK") < [r["code"] for r in rows].index("DEAD_STOCK")


@pytest.mark.django_db
def test_attention_snooze_hides_and_expiry_unhides(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="ATT-SNZ", purchase_price="80")
    add_stock(tenant_a, product, "10")
    _complete_non_gst(tenant_a, customer, product, price="50")  # below cost

    cu = tenant_a.company.memberships.get(user=tenant_a.owner)
    rows = build_attention_rows(tenant_a.company, company_user=cu)
    below = next(r for r in rows if r["code"] == "SALE_BELOW_COST")
    snooze_attention_row(
        tenant_a.company, cu, dedupe_key=below["dedupe_key"], days=7, reason="Checking with CA",
    )
    hidden = build_attention_rows(tenant_a.company, company_user=cu)
    assert below["dedupe_key"] not in {r["dedupe_key"] for r in hidden}

    state = AttentionRowState.objects.get(company=tenant_a.company, dedupe_key=below["dedupe_key"])
    state.snooze_until = timezone.now() - timedelta(minutes=1)
    state.save(update_fields=["snooze_until"])
    shown = build_attention_rows(tenant_a.company, company_user=cu)
    assert below["dedupe_key"] in {r["dedupe_key"] for r in shown}


@pytest.mark.django_db
def test_attention_cashier_hides_margin_leakage(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="ATT-CASH", purchase_price="80")
    add_stock(tenant_a, product, "10")
    _complete_non_gst(tenant_a, customer, product, price="50")

    owner_cu = tenant_a.company.memberships.get(user=tenant_a.owner)
    staff_cu = tenant_a.company.memberships.get(user=tenant_a.staff)
    owner_codes = {r["code"] for r in build_attention_rows(tenant_a.company, company_user=owner_cu)}
    staff_codes = {r["code"] for r in build_attention_rows(tenant_a.company, company_user=staff_cu)}
    assert "SALE_BELOW_COST" in owner_codes
    assert "SALE_BELOW_COST" not in staff_codes


@pytest.mark.django_db
def test_attention_api_and_snooze_reason_required(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="ATT-API", purchase_price="80")
    add_stock(tenant_a, product, "5")
    _complete_non_gst(tenant_a, customer, product, price="50")

    resp = tenant_a.client.get("/api/v1/insights/attention/")
    assert resp.status_code == 200, resp.data
    body = resp.data.get("data") or resp.data
    rows = body.get("rows") or body.get("Rows")
    assert rows
    sample = rows[0]
    # HTTP layer camelCases; Python contract is snake_case.
    keys = set(sample.keys())
    assert "code" in keys and ("dedupeKey" in keys or "dedupe_key" in keys)
    dedupe = sample.get("dedupeKey") or sample.get("dedupe_key")

    bad = tenant_a.client.post(
        "/api/v1/insights/attention/snooze/",
        {"dedupe_key": dedupe, "days": 7},
        format="json",
    )
    assert bad.status_code == 400

    ok = tenant_a.client.post(
        "/api/v1/insights/attention/snooze/",
        {"dedupe_key": dedupe, "days": 7, "reason": "Follow up next week"},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    again = tenant_a.client.get("/api/v1/insights/attention/")
    again_body = again.data.get("data") or again.data
    assert dedupe not in {
        r.get("dedupeKey") or r.get("dedupe_key") for r in again_body["rows"]
    }


@pytest.mark.django_db
def test_attention_tenant_isolation(tenant_a, tenant_b):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="ATT-ISO", purchase_price="80")
    add_stock(tenant_a, product, "5")
    _complete_non_gst(tenant_a, customer, product, price="50")

    cu_b = tenant_b.company.memberships.get(user=tenant_b.owner)
    rows_b = build_attention_rows(tenant_b.company, company_user=cu_b)
    assert "SALE_BELOW_COST" not in {r["code"] for r in rows_b}


@pytest.mark.django_db
def test_g19_dead_stock_ignores_fully_reserved_stock(tenant_a):
    """G-19: DEAD_STOCK must be reserved-aware (on_hand - reserved), matching
    low_stock_alert_payload and the health-score stock_score. A SKU that is
    fully reserved against an open sales order has zero *available* stock and
    must not be flagged (or money-valued) as dead."""
    from sales.models import SalesInvoice, SalesOrder
    from sales.notes_services import SalesNotesService

    product = make_product(tenant_a.company, sku="ATT-RESERVED", purchase_price="50", reorder_level="0")
    add_stock(tenant_a, product, "40", unit_cost="50")
    customer = make_customer(tenant_a.company)

    order = SalesOrder.objects.create(
        company=tenant_a.company,
        customer=customer,
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal("40"), "unit_price": Decimal("90"), "gst_rate": 0}],
        tenant_a.owner,
    )
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONFIRMED

    cu = tenant_a.company.memberships.get(user=tenant_a.owner)
    rows = build_attention_rows(tenant_a.company, company_user=cu)
    codes = {r["code"] for r in rows}
    assert "DEAD_STOCK" not in codes


def test_assignment_overdue_is_a_marker_and_mine_keeps_the_owner(tenant_a):
    from datetime import timedelta

    from accounts.models import CompanyUser
    from insights.attention import _attach_assignment, assign_attention_row

    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_ACTION_ASSIGNMENT"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    member = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.owner)
    today = timezone.localdate()
    assign_attention_row(
        tenant_a.company,
        member,
        dedupe_key="MINE-1",
        assignee_id=member.id,
        due_date=(today - timedelta(days=1)).isoformat(),
    )
    raw = [{"dedupe_key": "MINE-1", "severity": "warning", "code": "LOW_STOCK_FAST_MOVER"}]
    attached = _attach_assignment(tenant_a.company, raw)
    assert attached[0]["overdue"] is True
    assert attached[0]["severity"] == "warning"
    mine = [row for row in attached if row.get("assigned_to") == member.id]
    assert len(mine) == 1
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    hidden = _attach_assignment(tenant_a.company, [{"dedupe_key": "MINE-1", "severity": "warning"}])
    assert "assigned_to" not in hidden[0]
    assert "overdue" not in hidden[0]
