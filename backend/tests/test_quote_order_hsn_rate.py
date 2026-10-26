"""BB-100 F1: quotations and sales orders take the HSN-table GST rate, like the invoice.

Before the fix only sales and purchase invoices were re-rated, so a product whose own rate
disagreed with the HSN table was quoted at one GST total and invoiced at another, while the
quote editor's live preview (which is re-rated) showed a third figure to the user.
"""

from datetime import date
from decimal import Decimal

import pytest

from masters.models import HsnRate
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db

# Not in the seeded starter table, so this row is the only one that can match.
HSN = "554433"


@pytest.fixture
def setup(tenant_a):
    HsnRate.objects.create(hsn_sac=HSN, rate=Decimal("18"), valid_from=date(2020, 1, 1), version="t1")
    product = make_product(tenant_a.company, sku="F1-1", hsn_code=HSN, gst_rate="12", selling_price="100")
    customer = make_customer(tenant_a.company, name="F1 buyer", state="Karnataka")
    return tenant_a, product, customer


def _line(product):
    return {"product": product, "quantity": Decimal("1"), "unit_price": Decimal("100"), "gst_rate": Decimal("12")}


def test_quotation_uses_hsn_table_rate_and_records_the_notice(setup):
    from sales.services import SalesService

    tenant, product, customer = setup
    quote = SalesService.create_quotation(tenant.company, tenant.owner, {"customer": customer}, [_line(product)])
    item = quote.items.get()
    assert item.gst_rate == Decimal("18")
    assert item.applied_rate == Decimal("18")
    assert "12%→18% by HSN table" in item.rate_override_reason
    assert quote.grand_total == Decimal("118.00")


def test_sales_order_uses_hsn_table_rate(setup):
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService

    tenant, product, customer = setup
    order = SalesOrder.objects.create(
        company=tenant.company,
        customer=customer,
        created_by=tenant.owner,
        updated_by=tenant.owner,
    )
    SalesNotesService.set_order_items(order, [_line(product)], tenant.owner)
    order.refresh_from_db()
    assert order.items.get().gst_rate == Decimal("18")
    assert order.grand_total == Decimal("118.00")


def test_quote_editor_preview_matches_the_saved_quote(setup):
    tenant, product, customer = setup
    items = [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "12"}]
    preview = tenant.client.post(
        "/api/v1/sales/invoices/preview-totals/",
        {"customer": customer.id, "invoice_type": "GST", "items": items},
        format="json",
    )
    assert preview.status_code == 200, preview.data
    saved = tenant.client.post(
        "/api/v1/sales/quotations/",
        {"customer": customer.id, "invoice_type": "GST", "items": items},
        format="json",
    )
    assert saved.status_code == 201, saved.data
    assert Decimal(str(preview.data["grand_total"])) == Decimal(str(saved.data["grand_total"])) == Decimal("118.00")
    assert "by HSN table" in preview.data["items"][0]["rate_override_reason"]


def test_purchase_order_uses_hsn_table_rate(setup):
    from purchases.models import PurchaseOrder
    from purchases.notes_services import PurchaseNotesService
    from tests.conftest import make_supplier

    tenant, product, _ = setup
    supplier = make_supplier(tenant.company, name="F1 supplier", state="Karnataka")
    order = PurchaseOrder.objects.create(
        company=tenant.company,
        supplier=supplier,
        created_by=tenant.owner,
        updated_by=tenant.owner,
    )
    PurchaseNotesService.set_order_items(order, [_line(product)], tenant.owner)
    order.refresh_from_db()
    assert order.items.get().gst_rate == Decimal("18")
    assert order.grand_total == Decimal("118.00")


def test_purchase_order_preview_rates_on_the_order_date(setup):
    from tests.conftest import make_supplier

    tenant, product, _ = setup
    supplier = make_supplier(tenant.company, name="F1 supplier", state="Karnataka")
    preview = tenant.client.post(
        "/api/v1/purchases/invoices/preview-totals/",
        {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "order_date": "2026-10-01",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "12"}],
        },
        format="json",
    )
    assert preview.status_code == 200, preview.data
    assert Decimal(str(preview.data["grand_total"])) == Decimal("118.00")
    assert "by HSN table" in preview.data["items"][0]["rate_override_reason"]
