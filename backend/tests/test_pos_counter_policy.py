"""POS checkout rules: tender accounts, credit, walk-in, and the till trace."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.hashers import make_password

from accounting.models import JournalLine
from inventory.models import BatchLot, StockBalance
from payments.models import CustomerReceipt
from sales.models import SalesInvoice
from tests.conftest import add_stock, make_customer, make_product, map_pos_tender

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


def _debit_codes(company, receipt_id):
    return list(
        JournalLine.objects.filter(
            entry__company=company,
            entry__source_type="CUSTOMER_RECEIPT",
            entry__source_id=receipt_id,
            entry__purpose="CREATE",
            debit__gt=0,
        ).values_list("account__code", flat=True)
    )


def test_cash_posts_to_1100_and_upi_posts_to_the_mapped_bank(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="POS-CASH-1100", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    cash = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert cash.status_code == 201, cash.data
    cash_receipt = CustomerReceipt.objects.get(pk=cash.data["receipt"]["id"])
    assert cash_receipt.bank_account_id is None
    assert _debit_codes(tenant_a.company, cash_receipt.id) == ["1100"]

    bank = map_pos_tender(tenant_a.company, "UPI")
    product_u = make_product(tenant_a.company, sku="POS-UPI-BANK", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product_u, "5")
    missing = _checkout(tenant_a, customer, product_u, {"mode": "CARD", "amount": "100.00"})
    assert missing.status_code == 400, missing.data
    assert SalesInvoice.objects.filter(company=tenant_a.company, customer=customer, items__product=product_u).count() == 0

    upi = _checkout(tenant_a, customer, product_u, {"mode": "UPI", "amount": "100.00", "reference": "UTR1"})
    assert upi.status_code == 201, upi.data
    upi_receipt = CustomerReceipt.objects.get(pk=upi.data["receipt"]["id"])
    assert upi_receipt.bank_account_id == bank.id
    codes = _debit_codes(tenant_a.company, upi_receipt.id)
    assert codes and "1100" not in codes


def test_credit_skips_the_receipt_and_uses_customer_terms(tenant_a):
    product = make_product(tenant_a.company, sku="POS-CREDIT", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5")
    named = make_customer(tenant_a.company, name="Anita", credit_days=7, credit_limit="500")
    ok = _checkout(tenant_a, named, product, {"mode": "CREDIT"})
    assert ok.status_code == 201, ok.data
    assert ok.data["receipt"] is None
    invoice = SalesInvoice.objects.get(pk=ok.data["invoice"]["id"])
    assert invoice.due_date == date(2026, 10, 7) + timedelta(days=7)
    assert invoice.payment_terms_days == 7
    assert CustomerReceipt.objects.filter(company=tenant_a.company, customer=named).count() == 0

    walk = make_customer(tenant_a.company, name="Counter walk-in", is_pos_walk_in=True)
    blocked = _checkout(tenant_a, walk, product, {"mode": "CREDIT"})
    assert blocked.status_code == 400, blocked.data
    assert "pos_credit_walk_in" in str(blocked.data)


def test_cash_sale_does_not_trip_a_limit_the_receipt_clears(tenant_a):
    product = make_product(tenant_a.company, sku="POS-LIMIT", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Limited", credit_limit="50")
    cash = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert cash.status_code == 201, cash.data
    product2 = make_product(tenant_a.company, sku="POS-LIMIT-CR", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product2, "5")
    credit = _checkout(tenant_a, customer, product2, {"mode": "CREDIT"})
    assert credit.status_code == 400, credit.data


def test_gstin_bill_discount_is_forced_before_tax(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    product = make_product(tenant_a.company, sku="POS-GSTIN-DISC", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="Karnataka", gstin="29AAAAA0000A1Z5")
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "RETAIL",
                "invoice_date": "2026-10-07",
                "invoice_discount": "10.00",
                "invoice_discount_mode": "AFTER_TAX",
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "0",
                }],
            },
            "payment": {"mode": "CASH", "amount": "90.00"},
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    invoice = SalesInvoice.objects.get(pk=resp.data["invoice"]["id"])
    assert invoice.invoice_discount_mode == SalesInvoice.DiscountMode.BEFORE_TAX


def test_discount_above_the_cap_needs_the_owner_pin(tenant_a):
    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_max_line_discount"] = "10"
    flags["pos_owner_pin_hash"] = make_password("2468")
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    product = make_product(tenant_a.company, sku="POS-CAP", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    body_items = [{
        "product": product.id,
        "quantity": "1",
        "unit_price": "100.00",
        "gst_rate": "0",
        "discount_percent": "25",
    }]
    blocked = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": "2026-10-07",
                "items": body_items,
            },
            "payment": {"mode": "CASH", "amount": "75.00"},
        },
        format="json",
    )
    assert blocked.status_code == 400, blocked.data
    assert "pos_discount_cap" in str(blocked.data)
    allowed = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": "2026-10-07",
                "items": body_items,
            },
            "payment": {"mode": "CASH", "amount": "75.00"},
            "owner_pin": "2468",
        },
        format="json",
    )
    assert allowed.status_code == 201, allowed.data


def test_expired_lot_is_blocked_until_a_reason_is_allowed(tenant_a):
    product = make_product(tenant_a.company, sku="POS-EXP", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5")
    BatchLot.objects.create(
        company=tenant_a.company,
        product=product,
        batch_no="OLD",
        expiry_date=date(2020, 1, 1),
    )
    customer = make_customer(tenant_a.company)
    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_expired_lot_policy"] = "BLOCK"
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "invoice_date": "2026-10-07",
            "items": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "100.00",
                "gst_rate": "0",
                "batch_no": "OLD",
            }],
        },
        "payment": {"mode": "CASH", "amount": "100.00"},
    }
    blocked = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert blocked.status_code == 400, blocked.data
    flags["pos_expired_lot_policy"] = "REASON"
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    tenant_a.company.refresh_from_db()
    still = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert still.status_code == 400, still.data
    payload["expired_lot_reason"] = "Customer accepted the short-dated pack"
    ok = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert ok.status_code == 201, ok.data


def test_one_cash_sale_ties_stock_ledger_and_the_open_till(tenant_a):
    from django.utils import timezone

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="POS-TRACE", gst_rate="0", selling_price="80")
    add_stock(tenant_a, product, "4")
    customer = make_customer(tenant_a.company, name="Trace")
    today = timezone.localdate().isoformat()
    opened = tenant_a.client.post(
        "/api/v1/accounting/cash-shifts/",
        {"opening_float": "100.00", "business_date": today},
        format="json",
    )
    assert opened.status_code == 201, opened.data
    sale = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": today,
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "80.00",
                    "gst_rate": "0",
                }],
            },
            "payment": {"mode": "CASH", "amount": "80.00"},
        },
        format="json",
    )
    assert sale.status_code == 201, sale.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("3")
    receipt = CustomerReceipt.objects.get(pk=sale.data["receipt"]["id"])
    assert receipt.mode == "CASH"
    assert _debit_codes(tenant_a.company, receipt.id) == ["1100"]
    today = tenant_a.client.get("/api/v1/accounting/cash-shifts/today/")
    assert today.status_code == 200, today.data
    shift = today.data["shift"]
    assert Decimal(str(shift["expected_cash"])) == Decimal("180.00")


def test_under_cap_discount_is_audited(tenant_a):
    from core.models import AuditEvent

    product = make_product(tenant_a.company, sku="POS-DISC-AUDIT", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Discount audit")
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": "2026-10-07",
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "0",
                    "discount_percent": "5",
                }],
            },
            "payment": {"mode": "CASH", "amount": "95.00"},
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    event = AuditEvent.objects.filter(
        company=tenant_a.company, description="POS line discount.",
    ).first()
    assert event is not None
    assert event.metadata.get("above_cap") == []


def test_intra_state_gst_sale_stores_cgst_and_sgst(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    product = make_product(
        tenant_a.company, sku="POS-GST-SPLIT", gst_rate="18", selling_price="100", hsn_code="3402",
    )
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="GST counter", state="Karnataka")
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "GST",
                "invoice_date": "2026-10-07",
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "18",
                    "hsn_code": "3402",
                }],
            },
            "payment": {"mode": "CASH", "amount": "118.00"},
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    invoice = SalesInvoice.objects.get(pk=resp.data["invoice"]["id"])
    assert invoice.cgst_total > 0
    assert invoice.sgst_total > 0
    assert invoice.igst_total == 0
    line = invoice.items.get()
    assert line.cgst > 0
    assert line.sgst > 0
    assert line.igst == 0


def test_collect_uses_the_mapped_bank_and_cash_stays_on_1100(tenant_a):
    from django.utils import timezone

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="POS-COLLECT", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "4")
    customer = make_customer(tenant_a.company, name="Collect", credit_limit="1000", credit_days=7)
    credit = _checkout(tenant_a, customer, product, {"mode": "CREDIT"})
    assert credit.status_code == 201, credit.data
    invoice_id = credit.data["invoice"]["id"]
    cash = tenant_a.client.post(
        "/api/v1/sales/pos/collect/",
        {"invoice": invoice_id, "mode": "CASH", "amount": "100.00"},
        format="json",
    )
    assert cash.status_code == 201, cash.data
    cash_receipt = CustomerReceipt.objects.get(pk=cash.data["receipt"]["id"])
    assert cash_receipt.mode == "CASH"
    assert cash_receipt.bank_account_id is None
    assert cash_receipt.receipt_date == timezone.localdate()
    assert _debit_codes(tenant_a.company, cash_receipt.id) == ["1100"]

    product_u = make_product(tenant_a.company, sku="POS-COLLECT-UPI", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product_u, "2")
    credit_u = _checkout(tenant_a, customer, product_u, {"mode": "CREDIT"})
    assert credit_u.status_code == 201, credit_u.data
    bank = map_pos_tender(tenant_a.company, "UPI")
    upi = tenant_a.client.post(
        "/api/v1/sales/pos/collect/",
        {
            "invoice": credit_u.data["invoice"]["id"],
            "mode": "UPI",
            "amount": "100.00",
            "reference": "UTR-COLLECT",
        },
        format="json",
    )
    assert upi.status_code == 201, upi.data
    upi_receipt = CustomerReceipt.objects.get(pk=upi.data["receipt"]["id"])
    assert upi_receipt.bank_account_id == bank.id
    assert "1100" not in _debit_codes(tenant_a.company, upi_receipt.id)


def test_cashier_return_completes_without_the_cancel_permission(tenant_a):
    product = make_product(tenant_a.company, sku="POS-RETURN", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Return")
    sale = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("4")
    returned = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "exchange": True, "reason": "Counter exchange"},
        format="json",
    )
    assert returned.status_code == 201, returned.data
    assert returned.data["exchange"] is True
    assert returned.data["customer_id"] == customer.id
    from sales.models import SalesReturn

    row = SalesReturn.objects.get(pk=returned.data["id"])
    assert row.status == SalesReturn.Status.COMPLETED
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("5")
    again = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"]},
        format="json",
    )
    assert again.status_code == 400, again.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("5")


def test_closed_period_is_reported_without_creating_a_row(tenant_a):
    from django.utils import timezone

    from reporting.models import GstReturnPeriod

    today = timezone.localdate()
    period = f"{today.year:04d}-{today.month:02d}"
    GstReturnPeriod.objects.create(
        company=tenant_a.company, period=period, status=GstReturnPeriod.Status.CLOSED,
    )
    before = GstReturnPeriod.objects.filter(company=tenant_a.company).count()
    settings = tenant_a.client.get("/api/v1/sales/pos/settings/")
    assert settings.status_code == 200, settings.data
    assert settings.data["period_blocked"] is True
    assert period in settings.data["period_message"]
    assert GstReturnPeriod.objects.filter(company=tenant_a.company).count() == before
    product = make_product(tenant_a.company, sku="POS-PERIOD", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Closed period")
    blocked = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "invoice_date": today.isoformat(),
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "0",
                }],
            },
            "payment": {"mode": "CASH", "amount": "100.00"},
        },
        format="json",
    )
    assert blocked.status_code == 400, blocked.data


def test_a_short_split_is_not_treated_as_fully_paid():
    from sales.pos_policy import settlement_marker

    marker = settlement_marker(None, [
        {"mode": "CASH", "amount": "40.00"},
        {"mode": "UPI", "amount": "10.00"},
    ])
    assert marker == Decimal("50.00")


def test_unknown_tender_is_refused(tenant_a):
    product = make_product(tenant_a.company, sku="POS-WIRE", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Wire")
    refused = _checkout(tenant_a, customer, product, {"mode": "WIRE", "amount": "100.00"})
    assert refused.status_code == 400, refused.data
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    assert SalesInvoice.objects.filter(company=tenant_a.company, customer=customer).count() == 0


def test_owner_pin_locks_after_repeated_wrong_guesses(tenant_a):
    from django.core.cache import cache

    from core.exceptions import BusinessRuleError
    from sales.pos_policy import PIN_MAX_FAILURES, pin_ok

    cache.delete(f"pos_pin_fail:{tenant_a.company.pk}:0")
    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_owner_pin_hash"] = make_password("2468")
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    for _ in range(PIN_MAX_FAILURES):
        assert pin_ok(tenant_a.company, "0000") is False
    with pytest.raises(BusinessRuleError):
        pin_ok(tenant_a.company, "2468")
    # A different user is not locked out by this user's guesses.
    class _Other:
        pk = 424242

    assert pin_ok(tenant_a.company, "2468", _Other()) is True
    cache.delete(f"pos_pin_fail:{tenant_a.company.pk}:0")
    assert pin_ok(tenant_a.company, "2468") is True


def test_company_payload_never_includes_the_pin_hash(tenant_a):
    from accounts.serializers import CompanySerializer

    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_owner_pin_hash"] = make_password("2468")
    flags["pos_max_line_discount"] = "10"
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    data = CompanySerializer(tenant_a.company).data
    assert "pos_owner_pin_hash" not in data["feature_flags"]
    assert data["feature_flags"]["pos_max_line_discount"] == "10"


def test_pos_settings_reject_a_foreign_bank_and_a_bad_discount(tenant_a):
    from core.exceptions import BusinessRuleError
    from sales.pos_policy import save_pos_settings

    with pytest.raises(BusinessRuleError):
        save_pos_settings(tenant_a.company, {"tender_accounts": {"UPI": 999999}})
    with pytest.raises(BusinessRuleError):
        save_pos_settings(tenant_a.company, {"max_line_discount": "150"})
    with pytest.raises(BusinessRuleError):
        save_pos_settings(tenant_a.company, {"max_line_discount": "abc"})
