"""Purchase review 2 (B-01 / B-02): the override refusals carry codes the app can act on."""

import re
from pathlib import Path

import pytest

from core.exceptions import BusinessRuleError
from purchases.pay_now import payment_error_payload


def test_payment_error_payload_keeps_the_specific_code_and_details():
    exc = BusinessRuleError("held", code="SUPPLIER_GSTIN_CANCELLED", extra={"cancelled_on": "2026-04-01"})
    payload = payment_error_payload(exc)
    assert payload["code"] == "SUPPLIER_GSTIN_CANCELLED"
    assert payload["details"] == {"cancelled_on": "2026-04-01"}


def test_payment_error_payload_plain_error_unchanged():
    payload = payment_error_payload(ValueError("boom"))
    assert payload == {"code": "payment_failed", "message": "The payment could not be recorded."}


def test_purchase_confirm_codes_are_the_ones_the_web_app_prompts():
    """Adding a confirm code here without a prompt in completeWithConfirms.ts strands the user."""
    from core.help_codes import HelpCode

    src = (Path(__file__).resolve().parents[1] / "purchases" / "services.py").read_text(encoding="utf8")
    used = set(re.findall(r"HelpCode\.([A-Z_]+)", src))
    codes = {getattr(HelpCode, name) for name in used}
    web = (
        Path(__file__).resolve().parents[2] / "web" / "src" / "utils" / "completeWithConfirms.ts"
    )
    if not web.exists():
        pytest.skip("web sources not present")
    web_src = web.read_text(encoding="utf8")
    confirm_codes = {c for c in codes if c.startswith("confirm_") or c == "place_of_supply_unresolved"}
    missing = [c for c in sorted(confirm_codes) if f"{c}:" not in web_src]
    assert not missing, f"no on-screen prompt for: {missing}"


# ---- end-to-end: the refusals the web app now turns into an approval dialog -----------------

from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

from tests.conftest import create_draft_purchase, make_product, make_supplier  # noqa: E402

pytestmark = pytest.mark.django_db
INV = "/api/v1/purchases/invoices"


def _bill_off_its_order(tenant):
    from purchases.models import PurchaseOrder, PurchaseOrderItem

    company = tenant.company
    supplier = make_supplier(company, gstin="29ZZZZZ5555Z1Z5")
    widget = make_product(company, name="Widget", sku="OVR-A", gst_rate="0", purchase_price="100")
    pur = create_draft_purchase(tenant, supplier, [
        {"product": widget.id, "quantity": "10", "unit_price": "120", "gst_rate": "0"},
    ])
    order = PurchaseOrder.objects.create(
        company=company, supplier=supplier, created_by=tenant.owner, updated_by=tenant.owner,
    )
    PurchaseOrderItem.objects.create(
        company=company, purchase_order=order, product=widget,
        quantity=Decimal("10"), unit_price=Decimal("100.00"), gst_rate=Decimal("0"),
    )
    order.converted_purchase_id = pur["id"]
    order.save(update_fields=["converted_purchase"])
    return pur


def test_three_way_refusal_carries_a_code_the_owner_can_act_on(tenant_a):
    pur = _bill_off_its_order(tenant_a)
    blocked = tenant_a.client.post(f"{INV}/{pur['id']}/complete/")
    assert blocked.status_code == 400
    err = blocked.json()["error"]
    assert err["code"] == "THREE_WAY_MATCH_FAILED"
    assert err["details"]["canOverride"] is True
    assert any("Widget" in line for line in err["details"]["breaches"])
    assert "confirm_three_way_override" not in err["message"]  # no developer flag names on screen


def test_three_way_override_is_recorded_with_the_reason(tenant_a):
    from core.models import AuditEvent

    pur = _bill_off_its_order(tenant_a)
    done = tenant_a.client.post(
        f"{INV}/{pur['id']}/complete/",
        {"confirm_three_way_override": True, "three_way_reason": "Supplier raised the rate by phone"},
        format="json",
    )
    assert done.status_code == 200, done.data
    event = AuditEvent.objects.filter(description__startswith="3-way match difference approved").get()
    assert event.metadata["reason"] == "Supplier raised the rate by phone"
    assert event.metadata["breaches"]


def test_cancelled_gstin_block_is_coded_and_released_only_with_a_reason(tenant_a):
    company = tenant_a.company
    supplier = make_supplier(company, gstin="29ZZZZZ5555Z1Z5")
    supplier.gstin_cancelled_on = date(2020, 1, 1)
    supplier.save(update_fields=["gstin_cancelled_on"])
    product = make_product(company, name="Gadget", sku="OVR-G", gst_rate="0", purchase_price="10")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"},
    ])
    blocked = tenant_a.client.post(f"{INV}/{pur['id']}/complete/")
    assert blocked.status_code == 400
    err = blocked.json()["error"]
    assert err["code"] == "SUPPLIER_GSTIN_CANCELLED"
    assert err["details"]["cancelledOn"] == "2020-01-01"
    assert err["details"]["supplierName"] == supplier.name

    no_reason = tenant_a.client.post(f"{INV}/{pur['id']}/complete/", {"gstin_cancel_override": True}, format="json")
    assert no_reason.status_code == 400  # an override needs a written reason

    done = tenant_a.client.post(
        f"{INV}/{pur['id']}/complete/",
        {"gstin_cancel_override": True, "gstin_cancel_reason": "Re-registered, certificate on file"},
        format="json",
    )
    assert done.status_code == 200, done.data


def test_payment_to_a_cancelled_gstin_supplier_is_coded_and_can_be_released(tenant_a):
    company = tenant_a.company
    supplier = make_supplier(company, gstin="29ZZZZZ5555Z1Z5")
    product = make_product(company, name="Gizmo", sku="OVR-Z", gst_rate="0", purchase_price="10")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"},
    ], purchase_type="NON_GST")
    assert tenant_a.client.post(f"{INV}/{pur['id']}/complete/").status_code == 200
    supplier.gstin_cancelled_on = date(2020, 1, 1)
    supplier.save(update_fields=["gstin_cancelled_on"])

    held = tenant_a.client.post(
        f"{INV}/{pur['id']}/record-payment/", {"amount": "40", "mode": "CASH"}, format="json"
    )
    assert held.status_code == 400
    assert held.json()["error"]["code"] == "SUPPLIER_GSTIN_CANCELLED"

    paid = tenant_a.client.post(
        f"{INV}/{pur['id']}/record-payment/",
        {"amount": "40", "mode": "CASH", "gstin_hold_override": True, "gstin_hold_reason": "Owner approved"},
        format="json",
    )
    assert paid.status_code == 201, paid.data


def test_supplier_ledger_rows_name_their_document_and_a_dated_statement_has_an_opening_balance(tenant_a):
    company = tenant_a.company
    supplier = make_supplier(company)
    product = make_product(company, name="Thing", sku="OVR-T", gst_rate="0", purchase_price="10")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"},
    ], purchase_type="NON_GST")
    assert tenant_a.client.post(f"{INV}/{pur['id']}/complete/").status_code == 200

    resp = tenant_a.client.get(f"/api/v1/ledgers/suppliers/{supplier.id}/")
    assert resp.status_code == 200
    data = resp.data
    assert Decimal(str(data["opening_balance"])) == 0
    row = data["entries"][0]
    assert row["source_id"] == pur["id"]

    later = tenant_a.client.get(f"/api/v1/ledgers/suppliers/{supplier.id}/", {"date_from": "2999-01-01"})
    assert Decimal(str(later.data["opening_balance"])) == Decimal("100")
    assert later.data["entries"] == []
