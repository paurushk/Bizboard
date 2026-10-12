"""QOE-12a / QOE-00 / QOE-01: sales-order guard parity, idempotency, defaults and Quick Entry pricing.

See docs/QUICK_ORDER_ENTRY_IMPLEMENTATION_PLAN.md.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import AuditEvent
from inventory.models import StockBalance
from masters.models import Customer, CustomerShippingAddress, PriceList, PriceListItem
from sales.models import SalesInvoice, SalesOrder
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db

ORDERS = "/api/v1/sales/orders/"


def _order_payload(customer, product, **extra):
    return {"customer": customer.id, "items": [{"product": product.id, "quantity": "2"}], **extra}


@pytest.fixture
def setup(tenant_a):
    from accounts.models import CompanyUser

    CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.staff).update(can_create_sales=True)
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    return tenant_a, customer, product


# ---------- customer status gate ----------

@pytest.mark.parametrize("status", [Customer.Status.BLOCKED, Customer.Status.INACTIVE])
def test_order_create_rejects_inactive_customer(setup, status):
    tenant, customer, product = setup
    customer.status = status
    customer.save(update_fields=["status"])
    resp = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    assert resp.status_code == 400, resp.data
    assert not SalesOrder.objects.filter(company=tenant.company).exists()


def test_confirm_rejects_customer_blocked_after_draft_and_reserves_nothing(setup):
    tenant, customer, product = setup
    add_stock(tenant, product, "10")
    created = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    assert created.status_code == 201, created.data
    customer.status = Customer.Status.BLOCKED
    customer.save(update_fields=["status"])
    resp = tenant.client.post(f"{ORDERS}{created.data['id']}/confirm/", {}, format="json")
    assert resp.status_code == 400, resp.data
    assert "customer_not_active" in str(resp.data)
    bal = StockBalance.objects.filter(company=tenant.company, product=product).first()
    assert bal is None or bal.reserved == 0


def test_draft_for_now_blocked_customer_can_still_be_edited(setup):
    tenant, customer, product = setup
    created = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    customer.status = Customer.Status.BLOCKED
    customer.save(update_fields=["status"])
    resp = tenant.client.patch(f"{ORDERS}{created.data['id']}/", {"notes": "hold"}, format="json")
    assert resp.status_code == 200, resp.data


def test_challan_create_rejects_blocked_customer(setup):
    tenant, customer, product = setup
    customer.status = Customer.Status.BLOCKED
    customer.save(update_fields=["status"])
    resp = tenant.client.post(
        "/api/v1/sales/delivery-challans/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "1"}]},
        format="json",
    )
    assert resp.status_code == 400, resp.data


# ---------- subscription gate ----------

def test_lapsed_subscription_blocks_order_and_challan_writes_but_not_reads(setup, settings):
    from billing.models import Plan, Subscription

    tenant, customer, product = setup
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "SubscriptionWriteGate" not in m]
    plan = Plan.objects.create(name="QOE", slug="qoe-lapsed", seat_limit=3, price_paise=0)
    Subscription.objects.create(
        company=tenant.company,
        plan=plan,
        status=Subscription.Status.PAST_DUE,
        current_period_end=timezone.now() - timedelta(days=1),
    )
    resp = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    assert resp.status_code in (402, 403), resp.data
    resp = tenant.client.post(
        "/api/v1/sales/delivery-challans/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "1"}]},
        format="json",
    )
    assert resp.status_code in (402, 403), resp.data
    assert tenant.client.get(ORDERS).status_code == 200


# ---------- idempotency ----------

def test_order_create_idempotency_key_replays_one_row(setup):
    tenant, customer, product = setup
    kw = {"HTTP_IDEMPOTENCY_KEY": "qe-order-1"}
    first = tenant.client.post(ORDERS, _order_payload(customer, product), format="json", **kw)
    second = tenant.client.post(ORDERS, _order_payload(customer, product), format="json", **kw)
    assert first.status_code == 201, first.data
    assert second.status_code in (200, 201), second.data
    assert SalesOrder.objects.filter(company=tenant.company).count() == 1
    assert second.data.get("id") == first.data.get("id") or second.data == first.data


def test_failed_order_create_releases_key_so_corrected_retry_succeeds(setup):
    tenant, customer, product = setup
    kw = {"HTTP_IDEMPOTENCY_KEY": "qe-order-2"}
    bad = tenant.client.post(ORDERS, {"customer": customer.id, "items": []}, format="json", **kw)
    assert bad.status_code == 400, bad.data
    ok = tenant.client.post(ORDERS, _order_payload(customer, product), format="json", **kw)
    assert ok.status_code == 201, ok.data


def test_order_confirm_idempotent_and_already_confirmed_code(setup):
    tenant, customer, product = setup
    add_stock(tenant, product, "10")
    created = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    url = f"{ORDERS}{created.data['id']}/confirm/"
    kw = {"HTTP_IDEMPOTENCY_KEY": "qe-confirm-1"}
    first = tenant.client.post(url, {}, format="json", **kw)
    assert first.status_code == 200, first.data
    replay = tenant.client.post(url, {}, format="json", **kw)
    assert replay.status_code == 200, replay.data
    bal = StockBalance.objects.get(company=tenant.company, product=product)
    assert bal.reserved == Decimal("2")  # reserved once
    again = tenant.client.post(url, {}, format="json")
    assert again.status_code == 400
    assert "order_already_confirmed" in str(again.data)


# ---------- audit source ----------

def test_audit_source_header_is_allow_listed(setup):
    tenant, customer, product = setup
    ok = tenant.client.post(
        ORDERS, _order_payload(customer, product), format="json", HTTP_X_CLIENT_SOURCE="quick_entry"
    )
    assert ok.status_code == 201, ok.data
    other = tenant.client.post(
        ORDERS, _order_payload(customer, product), format="json", HTTP_X_CLIENT_SOURCE="evil<script>"
    )
    assert other.status_code == 201, other.data
    events = AuditEvent.objects.filter(company=tenant.company, entity_type="SalesOrder", action="CREATE")
    sources = sorted(e.metadata.get("source") for e in events)
    assert sources == ["quick_entry", "web"]


# ---------- defaults ----------

def test_order_defaults_from_customer(setup):
    tenant, customer, product = setup
    customer.credit_days = 30
    customer.shipping_address = "Legacy ship"
    customer.billing_address = "Bill"
    customer.save()
    resp = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["payment_terms_days"] == 30
    assert resp.data["delivery_address"] == "Legacy ship"

    default = CustomerShippingAddress.objects.create(
        company=tenant.company, customer=customer, label="Main", address="Default St", is_default=True
    )
    other = CustomerShippingAddress.objects.create(
        company=tenant.company, customer=customer, label="Alt", address="Alt Rd"
    )
    resp = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    assert resp.data["delivery_address"] == default.address
    resp = tenant.client.post(ORDERS, _order_payload(customer, product, ship_to=other.id), format="json")
    assert resp.data["delivery_address"] == "Alt Rd"
    # explicit values win
    resp = tenant.client.post(
        ORDERS,
        _order_payload(customer, product, delivery_address="Dock 9", payment_terms_days=0),
        format="json",
    )
    assert resp.data["delivery_address"] == "Dock 9"
    assert resp.data["payment_terms_days"] == 0


def test_order_falls_back_to_billing_address(setup):
    tenant, customer, product = setup
    customer.billing_address = "Bill only"
    customer.save()
    resp = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    assert resp.data["delivery_address"] == "Bill only"


def test_ship_to_of_another_customer_is_rejected(setup):
    tenant, customer, product = setup
    other_customer = make_customer(tenant.company, name="Other")
    foreign = CustomerShippingAddress.objects.create(
        company=tenant.company, customer=other_customer, label="X", address="Elsewhere"
    )
    resp = tenant.client.post(ORDERS, _order_payload(customer, product, ship_to=foreign.id), format="json")
    assert resp.status_code == 400, resp.data


# ---------- list filters ----------

def test_order_list_filters_customer_q_dates(setup):
    tenant, customer, product = setup
    other = make_customer(tenant.company, name="Zed Stores")
    a = tenant.client.post(ORDERS, _order_payload(customer, product), format="json").data
    b = tenant.client.post(ORDERS, _order_payload(other, product), format="json").data

    def ids(**params):
        rows = tenant.client.get(ORDERS, params).data
        rows = rows.get("results", rows) if isinstance(rows, dict) else rows
        return {r["id"] for r in rows}

    assert ids(customer=other.id) == {b["id"]}
    assert ids(q="Zed") == {b["id"]}
    assert ids(date_from="2999-01-01") == set()
    assert ids(date_to="2999-01-01") == {a["id"], b["id"]}
    assert tenant.client.get(ORDERS, {"date_from": "nope"}).status_code == 400


# ---------- QOE-00 pricing ----------

def _price_list(tenant, customer, product, price="80", min_qty="1"):
    plist = PriceList.objects.create(company=tenant.company, name="Wholesale")
    PriceListItem.objects.create(
        company=tenant.company, price_list=plist, product=product, unit_price=Decimal(price),
        min_qty=Decimal(min_qty),
    )
    customer.price_list = plist
    customer.save(update_fields=["price_list"])
    return plist


def test_quick_entry_items_without_price_use_price_list_and_live_gst(setup):
    tenant, customer, product = setup
    _price_list(tenant, customer, product, "80")
    product.gst_rate = Decimal("12")
    product.save(update_fields=["gst_rate"])
    resp = tenant.client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "1"}]},
        format="json",
        HTTP_X_CLIENT_SOURCE="quick_entry",
    )
    assert resp.status_code == 201, resp.data
    item = resp.data["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("80")
    assert Decimal(str(item["gst_rate"])) == Decimal("12")


def test_explicit_higher_price_is_still_honoured(setup):
    """B8-031 is intentional: a requested price above list stands. QOE-00 fixes the client."""
    tenant, customer, product = setup
    _price_list(tenant, customer, product, "80")
    resp = tenant.client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}]},
        format="json",
    )
    assert Decimal(str(resp.data["items"][0]["unit_price"])) == Decimal("100")


def test_quick_entry_invoice_gets_salesperson_and_audit_source(setup):
    tenant, customer, product = setup
    resp = tenant.staff_client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "1"}]},
        format="json",
        HTTP_X_CLIENT_SOURCE="quick_entry",
    )
    assert resp.status_code == 201, resp.data
    inv = SalesInvoice.objects.get(pk=resp.data["id"])
    assert inv.salesperson_id == tenant.staff.id
    event = AuditEvent.objects.filter(entity_type="SalesInvoice", entity_id=str(inv.pk), action="CREATE").first()
    assert event.metadata.get("source") == "quick_entry"
    # without the header nothing is defaulted
    plain = tenant.staff_client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "1"}]},
        format="json",
    )
    assert SalesInvoice.objects.get(pk=plain.data["id"]).salesperson_id is None


# ---------- QOE-01 preview ----------

PREVIEW = "/api/v1/sales/invoices/preview-totals/"


def test_preview_totals_resolves_customer_price_list_and_matches_saved_invoice(setup):
    tenant, customer, product = setup
    _price_list(tenant, customer, product, "80")
    body = {"customer": customer.id, "items": [{"product": product.id, "quantity": "3"}]}
    preview = tenant.client.post(PREVIEW, body, format="json")
    assert preview.status_code == 200, preview.data
    data = preview.data.get("data", preview.data)
    row = data["items"][0]
    assert Decimal(str(row["unit_price"])) == Decimal("80")
    assert row["applied_price_list_name"] == "Wholesale"
    saved = tenant.client.post("/api/v1/sales/invoices/", body, format="json").data
    for key in ("subtotal", "cgst_total", "sgst_total", "igst_total", "round_off", "grand_total"):
        assert Decimal(str(data[key])) == Decimal(str(saved[key])), key


def test_preview_totals_unchanged_without_customer_or_with_explicit_price(setup):
    tenant, customer, product = setup
    _price_list(tenant, customer, product, "80")
    no_customer = tenant.client.post(PREVIEW, {"items": [{"product": product.id, "quantity": "1"}]}, format="json")
    row = no_customer.data.get("data", no_customer.data)["items"][0]
    assert Decimal(str(row["unit_price"])) == Decimal("100")
    explicit = tenant.client.post(
        PREVIEW,
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "1", "unit_price": "95"}]},
        format="json",
    )
    row = explicit.data.get("data", explicit.data)["items"][0]
    assert Decimal(str(row["unit_price"])) == Decimal("95")


# ---------- QOE-03/06/07 support ----------

def test_products_ids_filter_and_unit_uqc(setup):
    tenant, _customer, product = setup
    other = make_product(tenant.company, name="Other", sku="OTH-1")
    resp = tenant.client.get("/api/v1/products/", {"ids": f"{product.id}"})
    rows = resp.data.get("results", resp.data) if isinstance(resp.data, dict) else resp.data
    assert [r["id"] for r in rows] == [product.id]
    assert "unit_uqc" in rows[0]
    assert tenant.client.get("/api/v1/products/", {"ids": "x"}).status_code == 400
    too_many = ",".join(str(i) for i in range(1, 52))
    assert tenant.client.get("/api/v1/products/", {"ids": too_many}).status_code == 400
    assert other.id not in [r["id"] for r in rows]


def test_quick_entry_recents_are_per_rep_and_active_only(setup):
    tenant, customer, product = setup
    blocked = make_customer(tenant.company, name="Blocked Co")
    body = lambda c: {"customer": c.id, "items": [{"product": product.id, "quantity": "1"}]}  # noqa: E731
    tenant.staff_client.post("/api/v1/sales/invoices/", body(customer), format="json")
    tenant.staff_client.post("/api/v1/sales/invoices/", body(blocked), format="json")
    tenant.client.post("/api/v1/sales/invoices/", body(make_customer(tenant.company, name="Owner Only")), format="json")
    blocked.status = Customer.Status.BLOCKED
    blocked.save(update_fields=["status"])

    resp = tenant.staff_client.get("/api/v1/sales/quick-entry/recents/")
    assert resp.status_code == 200, resp.data
    data = resp.data.get("data", resp.data)
    assert [c["name"] for c in data["customers"]] == [customer.name]
    assert [p["id"] for p in data["products"]] == [product.id]

    product.status = "INACTIVE"
    product.save(update_fields=["status"])
    data = tenant.staff_client.get("/api/v1/sales/quick-entry/recents/").data
    data = data.get("data", data)
    assert data["products"] == []


def test_rollout_report_lists_blank_address_and_blocked_customer_orders(setup):
    from io import StringIO

    from django.core.management import call_command

    tenant, customer, product = setup
    resp = tenant.client.post(ORDERS, _order_payload(customer, product, delivery_address=""), format="json")
    assert resp.status_code == 201
    SalesOrder.objects.filter(pk=resp.data["id"]).update(delivery_address="")
    customer.status = Customer.Status.BLOCKED
    customer.save(update_fields=["status"])
    out = StringIO()
    call_command("list_orders_for_quick_entry_rollout", company=tenant.company.id, stdout=out)
    text = out.getvalue()
    assert "No delivery address: 1" in text
    assert "Customer blocked/inactive: 1" in text


# ---------- QOE-12a: remaining planned tests ----------

def _multi_gstin(tenant):
    from accounts.models import CompanyGstin

    company = tenant.company
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.save()
    ka = CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True
    )
    mh = CompanyGstin.objects.create(
        company=company, gstin="27AAAAA0000A1Z2", state="Maharashtra", is_primary=False, is_active=True
    )
    return ka, mh


def test_order_tax_split_follows_the_branch_gstin_state(setup):
    tenant, _customer, product = setup
    ka, mh = _multi_gstin(tenant)
    mh_customer = make_customer(tenant.company, name="Pune Stores", state="Maharashtra")

    def totals(gstin):
        body = _order_payload(mh_customer, product, company_gstin=gstin.id)
        resp = tenant.client.post(ORDERS, body, format="json")
        assert resp.status_code == 201, resp.data
        return Decimal(str(resp.data["igst_total"])), Decimal(str(resp.data["cgst_total"]))

    igst_from_ka, cgst_from_ka = totals(ka)       # Karnataka -> Maharashtra: inter-state
    igst_from_mh, cgst_from_mh = totals(mh)       # Maharashtra -> Maharashtra: intra-state
    assert igst_from_ka > 0 and cgst_from_ka == 0
    assert cgst_from_mh > 0 and igst_from_mh == 0


def test_changed_body_with_a_reused_key_is_rejected_not_replayed(setup):
    tenant, customer, product = setup
    kw = {"HTTP_IDEMPOTENCY_KEY": "qe-order-reuse"}
    first = tenant.client.post(ORDERS, _order_payload(customer, product), format="json", **kw)
    assert first.status_code == 201, first.data
    other = tenant.client.post(
        ORDERS, {"customer": customer.id, "items": [{"product": product.id, "quantity": "9"}]}, format="json", **kw
    )
    assert other.status_code in (409, 422), other.data
    assert SalesOrder.objects.filter(company=tenant.company).count() == 1


def test_challan_create_is_idempotent_and_complete_refuses_a_blocked_customer(setup):
    from sales.models import DeliveryChallan

    tenant, customer, product = setup
    body = {"customer": customer.id, "items": [{"product": product.id, "quantity": "1"}]}
    kw = {"HTTP_IDEMPOTENCY_KEY": "qe-challan-1"}
    first = tenant.client.post("/api/v1/sales/delivery-challans/", body, format="json", **kw)
    second = tenant.client.post("/api/v1/sales/delivery-challans/", body, format="json", **kw)
    assert first.status_code == 201, first.data
    assert second.status_code in (200, 201), second.data
    assert DeliveryChallan.objects.filter(company=tenant.company).count() == 1

    customer.status = Customer.Status.BLOCKED
    customer.save(update_fields=["status"])
    done = tenant.client.post(f"/api/v1/sales/delivery-challans/{first.data['id']}/complete/")
    assert done.status_code == 400, done.data
    assert "customer_not_active" in str(done.data)


# ---------- D-6: orders carry a price mode ----------

def test_order_price_mode_changes_the_totals_and_carries_to_the_invoice(setup):
    tenant, customer, product = setup  # selling price 100, GST 18%
    excl = tenant.client.post(ORDERS, _order_payload(customer, product, price_mode="EXCLUSIVE"), format="json")
    incl = tenant.client.post(ORDERS, _order_payload(customer, product, price_mode="INCLUSIVE"), format="json")
    assert excl.status_code == 201 and incl.status_code == 201, (excl.data, incl.data)
    assert incl.data["price_mode"] == "INCLUSIVE"
    # 2 x 100: exclusive adds 18% on top; inclusive keeps 200 as the gross
    assert Decimal(str(excl.data["grand_total"])) == Decimal("236.00")
    assert Decimal(str(incl.data["grand_total"])) == Decimal("200.00")
    assert SalesOrder.objects.get(pk=incl.data["id"]).price_mode == "INCLUSIVE"
    # an order created without one is exclusive (existing behaviour)
    plain = tenant.client.post(ORDERS, _order_payload(customer, product), format="json")
    assert plain.data["price_mode"] == "EXCLUSIVE"


# ---------- QOE-15: flags ----------

def test_quick_entry_flags_default_off_and_flip_per_company(tenant_a, tenant_b):
    from core.services.feature_flags import flag_enabled

    keys = ("QUICK_ENTRY_ORDER_MODE", "QUICK_ENTRY_AUTO_CONFIRM", "QUICK_ENTRY_PRICE_PREVIEW")
    for key in keys:
        assert flag_enabled(tenant_a.company, key) is False
    tenant_a.company.feature_flags = {"QUICK_ENTRY_ORDER_MODE": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert flag_enabled(tenant_a.company, "QUICK_ENTRY_ORDER_MODE") is True
    assert flag_enabled(tenant_a.company, "QUICK_ENTRY_AUTO_CONFIRM") is False
    assert flag_enabled(tenant_b.company, "QUICK_ENTRY_ORDER_MODE") is False


# ---------- customer collection status for the Quick Entry hold warning ----------

def test_customer_read_includes_collection_status_only_when_auto_hold_is_on(setup):
    tenant, customer, _product = setup
    url = f"/api/v1/customers/{customer.id}/"
    off = tenant.client.get(url)
    assert off.status_code == 200
    assert "collection_status" not in (off.data.get("data", off.data))

    tenant.company.auto_credit_hold_on_severe_overdue = True
    tenant.company.save(update_fields=["auto_credit_hold_on_severe_overdue"])
    on = tenant.client.get(url)
    assert on.status_code == 200, on.data
    assert "collection_status" in on.data.get("data", on.data)


# ---------- QOE-01: slab rules shared with the client fallback (web/src/utils/priceList.parity.test.ts) ----------

# (quantity, expected unit price or None when no slab applies) — keep identical to the web test.
SLAB_PARITY = [
    ("0.5", None),
    ("1", "100.00"),
    ("9", "100.00"),
    ("10", "90.00"),
    ("49", "90.00"),
    ("50", "72.00"),   # 80 less a 10% slab discount
    ("500", "72.00"),
]


@pytest.mark.parametrize("qty,expected", SLAB_PARITY)
def test_price_list_slab_resolution_table(setup, qty, expected):
    from masters.pricing import resolve_party_price

    tenant, customer, product = setup
    plist = PriceList.objects.create(company=tenant.company, name="Tiered")
    for min_qty, max_qty, price, disc in (("1", "9", "100", "0"), ("10", "49", "90", "0"), ("50", None, "80", "10")):
        PriceListItem.objects.create(
            company=tenant.company, price_list=plist, product=product, unit_price=Decimal(price),
            min_qty=Decimal(min_qty), max_qty=None if max_qty is None else Decimal(max_qty),
            discount_pct=Decimal(disc),
        )
    customer.price_list = plist
    customer.save(update_fields=["price_list"])
    price, name = resolve_party_price(customer=customer, product=product, quantity=Decimal(qty))
    if expected is None:
        assert price is None
    else:
        assert price == Decimal(expected)
        assert name == "Tiered"


def test_quick_entry_metrics_report_counts_source_tagged_documents(setup):
    from io import StringIO

    from django.core.management import call_command

    tenant, customer, product = setup
    body_order = _order_payload(customer, product)
    body_bill = {"customer": customer.id, "items": [{"product": product.id, "quantity": "1"}]}
    tenant.client.post(ORDERS, body_order, format="json", HTTP_X_CLIENT_SOURCE="quick_entry")
    tenant.client.post(ORDERS, body_order, format="json")  # not Quick Entry
    tenant.client.post("/api/v1/sales/invoices/", body_bill, format="json", HTTP_X_CLIENT_SOURCE="quick_entry")
    out = StringIO()
    call_command("quick_entry_metrics", company=tenant.company.id, stdout=out)
    text = out.getvalue()
    assert "documents in the last 14 days: 2" in text
    assert "sales orders: 1" in text and "draft bills:  1" in text
    assert "orders still DRAFT: 1 of 1" in text


def test_order_accepts_the_camelcase_body_the_web_app_sends(setup):
    """The browser sends camelCase (priceMode, shipTo, paymentTermsDays); the API must read it the same way."""
    tenant, customer, product = setup
    addr = CustomerShippingAddress.objects.create(
        company=tenant.company, customer=customer, label="Depot", address="Depot St"
    )
    resp = tenant.client.post(
        ORDERS,
        {
            "customer": customer.id,
            "invoiceType": "GST",
            "priceMode": "INCLUSIVE",
            "orderDate": "2026-10-12",
            "shipTo": addr.id,
            "notes": "deliver early",
            "items": [{"product": product.id, "quantity": 3}],
        },
        format="json",
        HTTP_X_CLIENT_SOURCE="quick_entry",
        HTTP_IDEMPOTENCY_KEY="camel-1",
    )
    assert resp.status_code == 201, resp.data
    order = SalesOrder.objects.get(pk=resp.data["id"])
    assert order.price_mode == "INCLUSIVE"
    assert order.delivery_address == "Depot St"
    assert order.notes == "deliver early"

    inv = tenant.client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "invoiceType": "GST", "priceMode": "INCLUSIVE", "items": [{"product": product.id, "quantity": 1}]},
        format="json",
        HTTP_X_CLIENT_SOURCE="quick_entry",
    )
    assert inv.status_code == 201, inv.data
    assert SalesInvoice.objects.get(pk=inv.data["id"]).price_mode == "INCLUSIVE"


def test_operators_can_turn_the_quick_entry_flags_on_and_off_with_grant_company_flag(tenant_a):
    from django.core.management import call_command

    from core.services.feature_flags import flag_enabled

    email = tenant_a.owner.email
    call_command("grant_company_flag", email=email, flag="QUICK_ENTRY_ORDER_MODE", on=True)
    tenant_a.company.refresh_from_db()
    assert flag_enabled(tenant_a.company, "QUICK_ENTRY_ORDER_MODE") is True
    call_command("grant_company_flag", email=email, flag="QUICK_ENTRY_ORDER_MODE", off=True)
    tenant_a.company.refresh_from_db()
    assert flag_enabled(tenant_a.company, "QUICK_ENTRY_ORDER_MODE") is False


def test_quotation_converts_to_an_exclusive_order_with_the_same_total(setup):
    """SalesOrder.price_mode switched on the quotation->order copy; an ordinary quotation must not change."""
    tenant, customer, product = setup
    quote = tenant.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert quote.status_code == 201, quote.data
    order = tenant.client.post(f"/api/v1/sales/quotations/{quote.data['id']}/convert-to-order/", {}, format="json")
    assert order.status_code == 200, order.data
    assert order.data["price_mode"] == "EXCLUSIVE"
    assert Decimal(str(order.data["grand_total"])) == Decimal(str(quote.data["grand_total"]))


def test_choosing_ship_to_on_an_edit_updates_the_delivery_address(setup):
    tenant, customer, product = setup
    addr = CustomerShippingAddress.objects.create(
        company=tenant.company, customer=customer, label="Depot", address="Depot St"
    )
    created = tenant.client.post(ORDERS, _order_payload(customer, product, delivery_address="Old Rd"), format="json")
    assert created.status_code == 201, created.data
    resp = tenant.client.patch(f"{ORDERS}{created.data['id']}/", {"ship_to": addr.id}, format="json")
    assert resp.status_code == 200, resp.data
    assert SalesOrder.objects.get(pk=created.data["id"]).delivery_address == "Depot St"
