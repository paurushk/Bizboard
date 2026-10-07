"""POS plan: refunds hit advances, shifts are per terminal, walk-in is not client-writable."""

from decimal import Decimal

import pytest
from django.contrib.auth.hashers import make_password

from accounting.models import JournalLine
from sales.models import PosCounterRefund, SalesInvoice
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _checkout(tenant, customer, product, payment, **extra):
    body = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "invoice_date": "2026-10-07",
            "items": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "100.00",
                "gst_rate": "0",
            }],
        },
        "payment": payment,
    }
    body.update(extra)
    return tenant.client.post("/api/v1/sales/invoices/pos-checkout/", body, format="json")


def _codes(company, source_type, source_id):
    lines = JournalLine.objects.filter(
        entry__company=company,
        entry__source_type=source_type,
        entry__source_id=source_id,
        entry__purpose="REFUND",
    )
    return sorted(
        (line.account.code, f"{line.debit:.2f}", f"{line.credit:.2f}")
        for line in lines
    )


def test_cash_return_debits_advances_and_credits_cash(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="POS-REFUND", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Refund me")
    sale = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    returned = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {
            "invoice": sale.data["invoice"]["id"],
            "refund_mode": "CASH",
            "reason": "Changed mind",
            "idempotency_key": "same-refund",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="same-refund",
    )
    assert returned.status_code == 201, returned.data
    refund = PosCounterRefund.objects.get(company=tenant_a.company)
    assert refund.mode == "CASH"
    assert refund.amount == Decimal("100.00")
    codes = _codes(tenant_a.company, "POS_REFUND", refund.id)
    assert ("2300", "100.00", "0.00") in codes
    assert ("1100", "0.00", "100.00") in codes
    again = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {
            "invoice": sale.data["invoice"]["id"],
            "refund_mode": "CASH",
            "idempotency_key": "same-refund",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="same-refund",
    )
    assert again.status_code == 200
    assert again.data["replayed"] is True
    assert PosCounterRefund.objects.filter(company=tenant_a.company).count() == 1


def test_walk_in_cannot_keep_the_advance(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="POS-WALK-REF", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    walk = make_customer(tenant_a.company, name="Counter walk-in", is_pos_walk_in=True)
    sale = _checkout(tenant_a, walk, product, {"mode": "CASH", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    refused = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "ADVANCE"},
        format="json",
    )
    assert refused.status_code == 400
    assert "pos_refund_walk_in" in str(refused.data)


def test_cash_is_refused_without_an_open_shift_when_required(tenant_a):
    tenant_a.company.accounting_enabled = True
    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_require_open_shift"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["accounting_enabled", "feature_flags"])
    product = make_product(tenant_a.company, sku="POS-SHIFT", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    refused = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert refused.status_code == 400
    assert "pos_shift_required" in str(refused.data)
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 0


def test_cashier_cannot_set_the_walk_in_flag(tenant_a):
    customer = make_customer(tenant_a.company, name="Ordinary")
    patched = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/",
        {"is_pos_walk_in": True},
        format="json",
    )
    assert patched.status_code == 200, patched.data
    customer.refresh_from_db()
    assert customer.is_pos_walk_in is False
    first = tenant_a.client.post("/api/v1/customers/pos-walk-in/", {}, format="json")
    second = tenant_a.client.post("/api/v1/customers/pos-walk-in/", {}, format="json")
    assert first.status_code in (200, 201), first.data
    assert second.status_code == 200, second.data
    assert first.data["id"] == second.data["id"]


def test_owner_pin_moves_to_a_row(tenant_a):
    from sales.models import PosApproverPin
    from sales.pos_policy import pin_ok, set_owner_pin

    set_owner_pin(tenant_a.company, "2468")
    tenant_a.company.refresh_from_db()
    assert "pos_owner_pin_hash" not in (tenant_a.company.feature_flags or {})
    assert PosApproverPin.objects.filter(company=tenant_a.company).count() == 1
    assert pin_ok(tenant_a.company, "2468")
    assert pin_ok(tenant_a.company, "0000") is False


def test_legacy_hash_still_matches(tenant_a):
    from sales.pos_policy import pin_ok

    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_owner_pin_hash"] = make_password("2468")
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    assert pin_ok(tenant_a.company, "2468") is True


def test_pos_catalog_returns_pos_fields(tenant_a):
    make_product(tenant_a.company, sku="CAT-1", selling_price="15")
    listed = tenant_a.client.get("/api/v1/products/pos-catalog/")
    assert listed.status_code == 200, listed.data
    row = next(item for item in listed.data["results"] if item["sku"] == "CAT-1")
    assert row["price"] == "15.00" or Decimal(row["price"]) == Decimal("15")
    assert "track_batch" in row


def _open_till(tenant):
    from django.utils import timezone

    opened = tenant.client.post(
        "/api/v1/accounting/cash-shifts/",
        {"opening_float": "100.00", "business_date": timezone.localdate().isoformat()},
        format="json",
    )
    assert opened.status_code == 201, opened.data
    return opened.data


def test_bank_return_credits_the_mapped_bank(tenant_a):
    from tests.conftest import map_pos_tender

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    map_pos_tender(tenant_a.company, "UPI")
    product = make_product(tenant_a.company, sku="POS-UPI-REF", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="UPI refund")
    sale = _checkout(tenant_a, customer, product, {"mode": "UPI", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    returned = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "BANK"},
        format="json",
    )
    assert returned.status_code == 201, returned.data
    refund = PosCounterRefund.objects.get(company=tenant_a.company)
    codes = _codes(tenant_a.company, "POS_REFUND", refund.id)
    assert ("1100", "0.00", "100.00") not in codes
    assert any(code != "2300" and credit == "100.00" for code, _debit, credit in codes)


def test_gateway_refund_does_not_post_a_counter_journal(tenant_a, monkeypatch):
    from payments.models import CustomerReceipt, GatewayPayment

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    from tests.conftest import map_pos_tender

    map_pos_tender(tenant_a.company, "UPI")
    product = make_product(tenant_a.company, sku="POS-GW", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Gateway")
    sale = _checkout(tenant_a, customer, product, {"mode": "UPI", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    receipt = CustomerReceipt.objects.get(pk=sale.data["receipt"]["id"])
    gateway = GatewayPayment.objects.create(
        company=tenant_a.company,
        provider="test",
        provider_payment_id="pay-pos-1",
        amount=Decimal("100.00"),
        status="CAPTURED",
    )
    receipt.gateway_payment = gateway
    receipt.save(update_fields=["gateway_payment"])
    monkeypatch.setattr(
        "payments.services.PaymentService.refund_gateway_payment",
        lambda **kwargs: kwargs,
    )
    returned = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "BANK"},
        format="json",
    )
    assert returned.status_code == 201, returned.data
    refund = PosCounterRefund.objects.get(company=tenant_a.company)
    assert refund.status == PosCounterRefund.Status.POSTED
    assert _codes(tenant_a.company, "POS_REFUND", refund.id) == []


def test_credit_return_only_accepts_advance(tenant_a):
    product = make_product(tenant_a.company, sku="POS-CR-REF", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Credit return")
    sale = _checkout(tenant_a, customer, product, {"mode": "CREDIT"})
    assert sale.status_code == 201, sale.data
    cash = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "CASH"},
        format="json",
    )
    assert cash.status_code == 400
    assert "pos_refund_empty" in str(cash.data)
    kept = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "ADVANCE"},
        format="json",
    )
    assert kept.status_code == 201, kept.data
    assert PosCounterRefund.objects.get(company=tenant_a.company).status == "ADVANCE"


def test_partial_payment_refund_is_capped_at_the_peeled_amount(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="POS-PART", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Partial")
    sale = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "40.00"})
    assert sale.status_code == 201, sale.data
    over = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "CASH", "refunds": [{"mode": "CASH", "amount": "100.00"}]},
        format="json",
    )
    assert over.status_code == 400
    assert "pos_refund_cap" in str(over.data)
    ok = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "CASH"},
        format="json",
    )
    assert ok.status_code == 201, ok.data
    assert PosCounterRefund.objects.get(company=tenant_a.company).amount == Decimal("40.00")


def test_cash_return_brings_expected_cash_back_to_the_float(tenant_a):
    from django.utils import timezone

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    _open_till(tenant_a)
    product = make_product(tenant_a.company, sku="POS-FLOAT", gst_rate="0", selling_price="80")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Float")
    today = timezone.localdate().isoformat()
    sale = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": today,
                "items": [{"product": product.id, "quantity": "1", "unit_price": "80.00", "gst_rate": "0"}],
            },
            "payment": {"mode": "CASH", "amount": "80.00"},
        },
        format="json",
    )
    assert sale.status_code == 201, sale.data
    returned = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "CASH"},
        format="json",
    )
    assert returned.status_code == 201, returned.data
    today_shift = tenant_a.client.get("/api/v1/accounting/cash-shifts/today/")
    assert Decimal(str(today_shift.data["shift"]["expected_cash"])) == Decimal("100.00")


def test_pilot_day_expected_cash_matches_receipts_refunds_and_drops(tenant_a):
    from django.utils import timezone

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    opened = _open_till(tenant_a)
    product = make_product(tenant_a.company, sku="POS-DAY", gst_rate="0", selling_price="80")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Pilot day")
    today = timezone.localdate().isoformat()
    sale = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": today,
                "items": [{"product": product.id, "quantity": "1", "unit_price": "80.00", "gst_rate": "0"}],
            },
            "payment": {"mode": "CASH", "amount": "80.00"},
        },
        format="json",
    )
    assert sale.status_code == 201, sale.data
    returned = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "CASH"},
        format="json",
    )
    assert returned.status_code == 201, returned.data
    dropped = tenant_a.client.post(
        f"/api/v1/accounting/cash-shifts/{opened['id']}/drop/",
        {"amount": "10.00", "note": "Safe"},
        format="json",
    )
    assert dropped.status_code == 200, dropped.data
    today_shift = tenant_a.client.get("/api/v1/accounting/cash-shifts/today/")
    assert Decimal(str(today_shift.data["shift"]["expected_cash"])) == Decimal("90.00")


def test_split_after_advance_does_not_collect_the_full_bill_again(tenant_a):
    from payments.models import CustomerReceipt, PaymentAllocation

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="POS-ADV-SPLIT", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "4")
    customer = make_customer(tenant_a.company, name="Advance split")
    sale = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    kept = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "ADVANCE"},
        format="json",
    )
    assert kept.status_code == 201, kept.data
    before = CustomerReceipt.objects.filter(company=tenant_a.company).count()
    again = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": "2026-10-07",
                "items": [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "0"}],
            },
            "apply_advance": "all",
            "payments": [
                {"mode": "CASH", "amount": "60.00"},
                {"mode": "CASH", "amount": "40.00"},
            ],
        },
        format="json",
    )
    assert again.status_code == 201, again.data
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == before
    allocated = PaymentAllocation.objects.filter(
        sales_invoice_id=again.data["invoice"]["id"], reversed_at__isnull=True,
    )
    assert sum((row.amount for row in allocated), Decimal("0")) == Decimal("100.00")


def test_retired_counter_events_are_rejected(tenant_a):
    refused = tenant_a.client.post(
        "/api/v1/sales/pos/events/",
        {"kind": "discount", "detail": "10 percent"},
        format="json",
    )
    assert refused.status_code == 400
    assert "pos_event_retired" in str(refused.data)


def test_invoice_payload_omits_pharmacy_fields(tenant_a):
    product = make_product(tenant_a.company, sku="POS-RX", gst_rate="0", selling_price="10")
    add_stock(tenant_a, product, "1")
    customer = make_customer(tenant_a.company)
    sale = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "10.00"})
    assert sale.status_code == 201, sale.data
    body = tenant_a.client.get(f"/api/v1/sales/invoices/{sale.data['invoice']['id']}/")
    assert body.status_code == 200
    assert "patient_name" not in body.data
    assert "prescriber_name" not in body.data
    assert "prescription_note" not in body.data


def test_till_payment_reduces_expected_cash_and_ties_to_the_cash_ledger(tenant_a):
    from django.db.models import Sum
    from django.utils import timezone

    from payments.models import SupplierPayment
    from tests.conftest import make_supplier

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    opened = _open_till(tenant_a)
    product = make_product(tenant_a.company, sku="POS-TILL-PAY", gst_rate="0", selling_price="80")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Till pay")
    today = timezone.localdate().isoformat()
    sale = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": today,
                "items": [{"product": product.id, "quantity": "1", "unit_price": "80.00", "gst_rate": "0"}],
            },
            "payment": {"mode": "CASH", "amount": "80.00"},
        },
        format="json",
    )
    assert sale.status_code == 201, sale.data
    returned = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "CASH"},
        format="json",
    )
    assert returned.status_code == 201, returned.data
    dropped = tenant_a.client.post(
        f"/api/v1/accounting/cash-shifts/{opened['id']}/drop/",
        {"amount": "10.00", "note": "Safe"},
        format="json",
    )
    assert dropped.status_code == 200, dropped.data
    supplier = make_supplier(tenant_a.company, name="Till supplier")
    paid = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {
            "supplier": supplier.id,
            "amount": "20.00",
            "mode": "CASH",
            "payment_date": today,
            "paid_from_till": True,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="till-supplier-20",
    )
    assert paid.status_code == 201, paid.data
    row = SupplierPayment.objects.get(pk=paid.data["id"])
    assert row.paid_from_till is True
    assert row.shift_id == opened["id"]
    today_shift = tenant_a.client.get("/api/v1/accounting/cash-shifts/today/")
    expected = Decimal(str(today_shift.data["shift"]["expected_cash"]))
    totals = JournalLine.objects.filter(company=tenant_a.company, account__code="1100").aggregate(
        debit=Sum("debit"), credit=Sum("credit"),
    )
    net_cash = Decimal(totals["debit"] or 0) - Decimal(totals["credit"] or 0)
    assert net_cash == Decimal("-20.00")
    assert expected == Decimal("100.00") + net_cash - Decimal("10.00")
    assert expected == Decimal("70.00")


def test_split_refund_follows_the_original_tenders(tenant_a):
    from tests.conftest import map_pos_tender

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    map_pos_tender(tenant_a.company, "UPI")
    product = make_product(tenant_a.company, sku="POS-SPLIT-REF", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Split refund")
    sale = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": "2026-10-07",
                "items": [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "0"}],
            },
            "payments": [
                {"mode": "CASH", "amount": "60.00"},
                {"mode": "UPI", "amount": "40.00"},
            ],
        },
        format="json",
    )
    assert sale.status_code == 201, sale.data
    returned = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "SPLIT"},
        format="json",
    )
    assert returned.status_code == 201, returned.data
    parts = {
        (row.mode, row.amount)
        for row in PosCounterRefund.objects.filter(company=tenant_a.company)
    }
    assert parts == {("CASH", Decimal("60.00")), ("BANK", Decimal("40.00"))}
    cash_refund = PosCounterRefund.objects.get(company=tenant_a.company, mode="CASH")
    bank_refund = PosCounterRefund.objects.get(company=tenant_a.company, mode="BANK")
    assert ("1100", "0.00", "60.00") in _codes(tenant_a.company, "POS_REFUND", cash_refund.id)
    bank_codes = _codes(tenant_a.company, "POS_REFUND", bank_refund.id)
    assert ("1100", "0.00", "40.00") not in bank_codes
    assert any(code != "2300" and credit == "40.00" for code, _debit, credit in bank_codes)


def test_offline_credit_cap_follows_the_outage(tenant_a):
    from django.utils import timezone

    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_offline_credit"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    product = make_product(tenant_a.company, sku="POS-OUTAGE", gst_rate="0", selling_price="3000")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="Outage credit")
    cached = timezone.now().isoformat()

    def bill(invoice_date, outage_id):
        return tenant_a.client.post(
            "/api/v1/sales/invoices/pos-checkout/",
            {
                "invoice": {
                    "customer": customer.id,
                    "invoice_type": "NON_GST",
                    "invoice_date": invoice_date,
                    "items": [{
                        "product": product.id,
                        "quantity": "1",
                        "unit_price": "3000.00",
                        "gst_rate": "0",
                    }],
                },
                "payment": {"mode": "CREDIT"},
                "offline_credit": True,
                "outage_id": outage_id,
                "credit_cached_at": cached,
                "terminal_id": "device-outage",
            },
            format="json",
        )

    first = bill("2026-10-06", "storm-1")
    assert first.status_code == 201, first.data
    second = bill("2026-10-07", "storm-1")
    assert second.status_code == 400, second.data
    assert "pos_offline_credit_cap" in str(second.data)
    other = bill("2026-10-07", "storm-2")
    assert other.status_code == 201, other.data


def test_signup_turns_the_open_shift_rule_on():
    import inspect

    from accounts.views import RegisterView

    source = inspect.getsource(RegisterView.post)
    assert '"pos_require_open_shift": True' in source


def test_gateway_refund_cannot_also_be_paid_as_cash(tenant_a, monkeypatch):
    from payments.models import CustomerReceipt, GatewayPayment

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    from tests.conftest import map_pos_tender

    map_pos_tender(tenant_a.company, "UPI")
    product = make_product(tenant_a.company, sku="POS-GW-TWICE", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Gateway twice")
    sale = _checkout(tenant_a, customer, product, {"mode": "UPI", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    receipt = CustomerReceipt.objects.get(pk=sale.data["receipt"]["id"])
    gateway = GatewayPayment.objects.create(
        company=tenant_a.company,
        provider="test",
        provider_payment_id="pay-pos-twice",
        amount=Decimal("100.00"),
        status="CAPTURED",
    )
    receipt.gateway_payment = gateway
    receipt.save(update_fields=["gateway_payment"])
    monkeypatch.setattr(
        "payments.services.PaymentService.refund_gateway_payment",
        lambda **kwargs: kwargs,
    )
    doubled = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {
            "invoice": sale.data["invoice"]["id"],
            "refunds": [
                {"mode": "BANK", "amount": "100.00"},
                {"mode": "CASH", "amount": "100.00"},
            ],
        },
        format="json",
    )
    assert doubled.status_code == 400, doubled.data
    assert "pos_refund_cap" in str(doubled.data)
    assert PosCounterRefund.objects.filter(company=tenant_a.company).count() == 0


def test_shorter_refund_key_does_not_replay_a_longer_one(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="POS-KEY", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Key prefix")
    first = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    second = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert first.status_code == 201 and second.status_code == 201
    short = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": first.data["invoice"]["id"], "refund_mode": "CASH", "idempotency_key": "ab"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="ab",
    )
    assert short.status_code == 201, short.data
    longer = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": second.data["invoice"]["id"], "refund_mode": "CASH", "idempotency_key": "abc"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="abc",
    )
    assert longer.status_code == 201, longer.data
    assert longer.data.get("replayed") is not True
    assert PosCounterRefund.objects.filter(company=tenant_a.company).count() == 2


def test_offline_card_sale_is_refused(tenant_a):
    from tests.conftest import map_pos_tender

    map_pos_tender(tenant_a.company, "UPI")
    product = make_product(tenant_a.company, sku="POS-OFF-UPI", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "1")
    customer = make_customer(tenant_a.company, name="Offline UPI")
    refused = _checkout(
        tenant_a, customer, product, {"mode": "UPI", "amount": "100.00"}, offline=True,
    )
    assert refused.status_code == 400, refused.data
    assert "pos_offline_tender" in str(refused.data)


def test_offline_credit_rejects_a_naive_or_future_cache_time(tenant_a):
    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_offline_credit"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    product = make_product(tenant_a.company, sku="POS-STALE", gst_rate="0", selling_price="10")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Stale cache")

    def bill(cached):
        return tenant_a.client.post(
            "/api/v1/sales/invoices/pos-checkout/",
            {
                "invoice": {
                    "customer": customer.id,
                    "invoice_type": "NON_GST",
                    "invoice_date": "2026-10-07",
                    "items": [{
                        "product": product.id,
                        "quantity": "1",
                        "unit_price": "10.00",
                        "gst_rate": "0",
                    }],
                },
                "payment": {"mode": "CREDIT"},
                "offline_credit": True,
                "credit_cached_at": cached,
            },
            format="json",
        )

    stale = bill("2020-01-01T00:00:00")
    assert stale.status_code == 400, stale.data
    assert "pos_offline_credit_stale" in str(stale.data)
    future = bill("2099-01-01T00:00:00")
    assert future.status_code == 400, future.data
    assert "pos_offline_credit_stale" in str(future.data)


def test_till_cash_is_not_counted_on_two_open_drawers(tenant_a):
    from django.utils import timezone

    from payments.models import SupplierPayment
    from tests.conftest import make_supplier

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    supplier = make_supplier(tenant_a.company, name="Unstamped till")
    today = timezone.localdate().isoformat()
    paid = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {
            "supplier": supplier.id,
            "amount": "20.00",
            "mode": "CASH",
            "payment_date": today,
            "paid_from_till": True,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="unstamped-till-20",
    )
    assert paid.status_code == 201, paid.data
    row = SupplierPayment.objects.get(pk=paid.data["id"])
    assert row.paid_from_till is True
    assert row.shift_id is None
    first = tenant_a.client.post(
        "/api/v1/accounting/cash-shifts/",
        {"opening_float": "100.00", "business_date": today, "terminal_id": "drawer-a"},
        format="json",
    )
    second = tenant_a.client.post(
        "/api/v1/accounting/cash-shifts/",
        {"opening_float": "100.00", "business_date": today, "terminal_id": "drawer-b"},
        format="json",
    )
    assert first.status_code == 201 and second.status_code == 201, (first.data, second.data)
    for terminal in ("drawer-a", "drawer-b"):
        body = tenant_a.client.get(f"/api/v1/accounting/cash-shifts/today/?terminal_id={terminal}")
        assert Decimal(str(body.data["shift"]["expected_cash"])) == Decimal("100.00")
    closed = tenant_a.client.post(
        f"/api/v1/accounting/cash-shifts/{first.data['id']}/close/",
        {"denominations": {"100": 1}},
        format="json",
    )
    assert closed.status_code == 200, closed.data
    left = tenant_a.client.get("/api/v1/accounting/cash-shifts/today/?terminal_id=drawer-b")
    assert Decimal(str(left.data["shift"]["expected_cash"])) == Decimal("80.00")
    ambiguous = tenant_a.client.post(
        "/api/v1/accounting/cash-shifts/",
        {"opening_float": "50.00", "business_date": today, "terminal_id": "drawer-c"},
        format="json",
    )
    assert ambiguous.status_code == 201, ambiguous.data
    refused = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {
            "supplier": supplier.id,
            "amount": "5.00",
            "mode": "CASH",
            "payment_date": today,
            "paid_from_till": True,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="two-tills",
    )
    assert refused.status_code == 400, refused.data
    assert "pos_till_ambiguous" in str(refused.data)
    assert SupplierPayment.objects.filter(company=tenant_a.company).count() == 1



def _offline_credit_bill(tenant, customer, product):
    return tenant.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": "2026-10-07",
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "10.00",
                    "gst_rate": "0",
                }],
            },
            "payment": {"mode": "CREDIT"},
            "offline_credit": True,
            "credit_cached_at": "2020-01-01T00:00:00",
        },
        format="json",
    )


def test_offline_credit_is_on_unless_the_owner_turns_it_off(tenant_a):
    product = make_product(tenant_a.company, sku="POS-OFFC-DEFAULT", gst_rate="0", selling_price="10")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="Default on")
    settings = tenant_a.client.get("/api/v1/sales/pos/settings/")
    assert settings.data["offline_credit"] is True
    # The switch is on, so the request gets past it and meets the next rule (a stale credit check).
    reached = _offline_credit_bill(tenant_a, customer, product)
    assert "pos_offline_credit_stale" in str(reached.data)
    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_offline_credit"] = False
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    assert tenant_a.client.get("/api/v1/sales/pos/settings/").data["offline_credit"] is False
    refused = _offline_credit_bill(tenant_a, customer, product)
    assert "pos_offline_credit_off" in str(refused.data)
