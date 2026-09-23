"""POS till total must not silently substitute an HSN catalog rate for a stale client total."""

from datetime import date
from decimal import Decimal

from django.db.models import Sum

from masters.models import HsnRate
from payments.models import PaymentAllocation
from sales.models import SalesInvoice
from tests.conftest import add_stock, make_customer, make_product


def test_pos_checkout_rejects_stale_client_total_when_hsn_rate_differs(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    product = make_product(
        tenant_a.company,
        sku="POS-HSN-MISMATCH",
        hsn_code="998811",
        gst_rate="12",
        selling_price="280",
    )
    add_stock(tenant_a, product, "10")
    HsnRate.objects.create(
        hsn_sac="998811",
        rate=Decimal("18"),
        cess=Decimal("0"),
        valid_from=date(2020, 1, 1),
        version="test-pos-mismatch",
    )
    customer = make_customer(tenant_a.company, state="Karnataka", gstin="29AAAAA0000A1Z5")

    preview = tenant_a.client.post(
        "/api/v1/sales/invoices/preview-totals/",
        {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-09-21",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "280.00",
                    "gst_rate": "12",
                }
            ],
        },
        format="json",
    )
    assert preview.status_code == 200, preview.data
    server_total = Decimal(str(preview.data["grand_total"]))
    stale_total = (Decimal("280") * Decimal("1.12")).quantize(Decimal("0.01"))
    assert server_total != stale_total

    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-09-21",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "280.00",
                    "gst_rate": "12",
                }
            ],
        },
        "payment": {
            "mode": "CASH",
            "amount": str(stale_total),
            "tendered_amount": str(stale_total),
            "expected_total": str(stale_total),
        },
    }
    blocked = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert blocked.status_code == 409, blocked.data
    assert SalesInvoice.objects.filter(company=tenant_a.company, customer=customer).count() == 0

    payload["payment"]["confirm_totals_mismatch"] = True
    payload["payment"]["expected_total"] = str(stale_total)
    ok = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert ok.status_code == 201, ok.data
    booked = Decimal(str(ok.data["invoice"]["grand_total"]))
    assert booked == server_total
    received = Decimal(str(ok.data["receipt"]["amount"]))
    assert received == stale_total


def test_pos_checkout_upi_walk_in_mismatch_requires_confirm(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    product = make_product(
        tenant_a.company,
        sku="POS-UPI-WALKIN",
        hsn_code="998822",
        gst_rate="12",
        selling_price="200",
    )
    add_stock(tenant_a, product, "10")
    HsnRate.objects.create(
        hsn_sac="998822",
        rate=Decimal("18"),
        cess=Decimal("0"),
        valid_from=date(2020, 1, 1),
        version="test-pos-upi-walkin",
    )
    customer = make_customer(
        tenant_a.company, name="Walk-in / Cash Customer", state="Karnataka",
    )

    preview = tenant_a.client.post(
        "/api/v1/sales/invoices/preview-totals/",
        {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-09-21",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "200.00", "gst_rate": "12"}
            ],
        },
        format="json",
    )
    assert preview.status_code == 200, preview.data
    server_total = Decimal(str(preview.data["grand_total"]))
    stale_total = (Decimal("200") * Decimal("1.12")).quantize(Decimal("0.01"))
    assert server_total != stale_total

    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-09-21",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "200.00", "gst_rate": "12"}
            ],
        },
        "payment": {
            "mode": "UPI",
            "amount": str(stale_total),
            "tendered_amount": str(stale_total),
            "expected_total": str(stale_total),
            "reference": "UPIWALK1",
        },
    }
    blocked = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert blocked.status_code == 409, blocked.data
    assert SalesInvoice.objects.filter(company=tenant_a.company, customer=customer).count() == 0

    payload["payment"]["confirm_totals_mismatch"] = True
    ok = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert ok.status_code == 201, ok.data
    assert Decimal(str(ok.data["invoice"]["grand_total"])) == server_total
    assert ok.data["receipt"]["mode"] == "UPI"


def test_pos_checkout_cash_walk_in_mismatch_requires_confirm(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    product = make_product(
        tenant_a.company,
        sku="POS-CASH-WALKIN",
        hsn_code="998833",
        gst_rate="12",
        selling_price="200",
    )
    add_stock(tenant_a, product, "10")
    HsnRate.objects.create(
        hsn_sac="998833",
        rate=Decimal("18"),
        cess=Decimal("0"),
        valid_from=date(2020, 1, 1),
        version="test-pos-cash-walkin",
    )
    walk_in = make_customer(tenant_a.company, name="Walk-in / Cash Customer", state="Karnataka")

    preview = tenant_a.client.post(
        "/api/v1/sales/invoices/preview-totals/",
        {
            "customer": walk_in.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-09-21",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "200.00", "gst_rate": "12"}
            ],
        },
        format="json",
    )
    assert preview.status_code == 200, preview.data
    server_total = Decimal(str(preview.data["grand_total"]))
    stale_total = (Decimal("200") * Decimal("1.12")).quantize(Decimal("0.01"))
    assert server_total != stale_total

    payload = {
        "invoice": {
            "customer": walk_in.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-09-21",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "200.00", "gst_rate": "12"}
            ],
        },
        "payment": {
            "mode": "CASH",
            "amount": str(stale_total),
            "tendered_amount": str(stale_total),
            "expected_total": str(stale_total),
        },
    }
    blocked = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert blocked.status_code == 409, blocked.data
    assert SalesInvoice.objects.filter(company=tenant_a.company, customer=walk_in).count() == 0

    payload["payment"]["confirm_totals_mismatch"] = True
    ok = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert ok.status_code == 201, ok.data
    assert Decimal(str(ok.data["invoice"]["grand_total"])) == server_total
    assert ok.data["receipt"]["mode"] == "CASH"


def test_pos_checkout_short_collect_zero_is_not_upgraded_to_full_total(tenant_a):
    """A deliberate short-collect of ₹0 (the totals-mismatch reconciliation
    dialog's "collect nothing now" choice) must be recorded as ₹0 received,
    not silently upgraded to the full invoice total because 0 is falsy in
    `payment_data.get("amount") or grand_total`."""
    product = make_product(tenant_a.company, sku="POS-SHORT-ZERO", selling_price="100")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)

    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-09-21",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "0"}],
        },
        "payment": {
            "mode": "CASH",
            "amount": 0,
            "tendered_amount": 0,
        },
    }
    ok = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert ok.status_code == 201, ok.data
    invoice_id = ok.data["invoice"]["id"]
    allocated = (
        PaymentAllocation.objects.filter(sales_invoice_id=invoice_id, reversed_at__isnull=True)
        .aggregate(total=Sum("amount"))["total"]
    )
    assert (allocated or Decimal("0")) == Decimal("0")
    invoice = SalesInvoice.objects.get(pk=invoice_id)
    assert invoice.grand_total == Decimal("100.00")
