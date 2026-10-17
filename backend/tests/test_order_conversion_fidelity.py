"""R3 (H-10, H-11; DEC-6): what an order is worth and what type it is survive every conversion.

An order priced tax-inclusive stores the exclusive price it extracted, so converting it must give
an invoice of the same total at every step. A Bill of Supply order stays a Bill of Supply.
"""

from decimal import Decimal

import pytest

from sales.models import SalesInvoice, SalesOrder
from sales.notes_services import SalesNotesService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _order(tenant, product, *, price="118", qty="1", invoice_type="GST", price_mode="EXCLUSIVE", gst="18"):
    customer = make_customer(tenant.company, name=f"Cust {SalesOrder.objects.count()}")
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "invoice_type": invoice_type,
            "price_mode": price_mode,
            "items": [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": gst}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return SalesOrder.objects.get(pk=resp.data["id"])


@pytest.fixture
def product(tenant_a):
    p = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, p, "100")
    return p


# ---------------------------------------------------------------------------
# H-10 — a tax-inclusive order keeps its total through every conversion
# ---------------------------------------------------------------------------


def test_tc_wp5_01_inclusive_order_to_invoice_keeps_the_total(tenant_a, product):
    order = _order(tenant_a, product, price_mode="INCLUSIVE")
    assert order.grand_total == Decimal("118.00")
    invoice = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    assert invoice.grand_total == Decimal("118.00")
    assert invoice.taxable_total == Decimal("100.00")


def test_tc_wp5_02_inclusive_order_to_challan_to_invoice_keeps_the_total(tenant_a, product):
    order = _order(tenant_a, product, price_mode="INCLUSIVE")
    challan = SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    assert challan.grand_total == Decimal("118.00")
    challan = SalesNotesService.complete_challan(challan, tenant_a.owner)
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    # Carrying INCLUSIVE onto this invoice took tax out of the price a second time: it read 100.
    assert invoice.grand_total == Decimal("118.00")
    assert invoice.taxable_total == Decimal("100.00")


def test_tc_wp5_02b_exclusive_order_is_unchanged(tenant_a, product):
    order = _order(tenant_a, product, price="100")
    assert order.grand_total == Decimal("118.00")
    invoice = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    assert invoice.grand_total == Decimal("118.00")


def test_tc_wp5_09_editing_an_inclusive_order_does_not_extract_tax_twice(tenant_a, product):
    order = _order(tenant_a, product, price_mode="INCLUSIVE")
    line = order.items.get()
    resp = tenant_a.client.patch(
        f"/api/v1/sales/orders/{order.id}/",
        {
            "items": [
                {
                    "id": line.id, "product": product.id, "quantity": "2",
                    "unit_price": str(line.unit_price), "gst_rate": "18",
                }
            ]
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    order.refresh_from_db()
    # 2 x 118 = 236. The editor sends back the stored exclusive price (100); extracting tax from
    # it again gave 200.
    assert order.grand_total == Decimal("236.00")
    assert order.price_mode == "INCLUSIVE"
    assert order.items.get().unit_price == Decimal("100.00")


def test_tc_wp5_03_quotation_to_order_to_invoice_keeps_the_quote_total(tenant_a, product):
    customer = make_customer(tenant_a.company, name="Quote Co")
    resp = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": customer.id,
            "valid_until": "2099-01-01",
            "items": [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    quote_total = Decimal(str(resp.data["grand_total"]))
    converted = tenant_a.client.post(f"/api/v1/sales/quotations/{resp.data['id']}/convert-to-order/", {}, format="json")
    assert converted.status_code == 200, converted.data
    order = SalesOrder.objects.get(pk=converted.data["id"])
    assert order.price_mode == "EXCLUSIVE"
    assert order.grand_total == quote_total
    invoice = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    assert invoice.grand_total == quote_total


# ---------------------------------------------------------------------------
# H-11 — a Bill of Supply order stays a Bill of Supply
# ---------------------------------------------------------------------------


def test_tc_wp5_04_non_gst_order_gives_an_untaxed_challan(tenant_a, product):
    order = _order(tenant_a, product, price="100", invoice_type="NON_GST", gst="0")
    challan = SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    assert challan.grand_total == Decimal("100.00")
    assert challan.cgst_total + challan.sgst_total + challan.igst_total == Decimal("0")


def test_tc_wp5_05_non_gst_order_challan_converts_to_a_non_gst_invoice(tenant_a, product):
    order = _order(tenant_a, product, price="100", invoice_type="NON_GST", gst="0")
    challan = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    assert invoice.invoice_type == SalesInvoice.InvoiceType.NON_GST  # a regular company used to get GST


def test_tc_wp5_06_gst_order_on_a_regular_company_stays_gst(tenant_a, product):
    order = _order(tenant_a, product, price="100")
    challan = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    assert challan.grand_total == Decimal("118.00")
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    assert invoice.invoice_type == SalesInvoice.InvoiceType.GST


def test_tc_wp5_07_standalone_challan_keeps_the_registration_rule(tenant_a, product):
    customer = make_customer(tenant_a.company, name="Walk-in Co")
    resp = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    done = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data
    converted = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{resp.data['id']}/convert/")
    assert converted.status_code == 200, converted.data
    assert converted.data["invoice_type"] == "GST"  # regular company with a GSTIN, as before


def test_tc_wp5_08_a_composition_company_still_gets_a_bill_of_supply(tenant_a, product):
    from accounts.models import Company

    tenant_a.company.registration_type = Company.RegistrationType.COMPOSITION
    tenant_a.company.save(update_fields=["registration_type"])
    order = _order(tenant_a, product, price="100", invoice_type="GST")
    challan = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    assert invoice.invoice_type == SalesInvoice.InvoiceType.NON_GST
