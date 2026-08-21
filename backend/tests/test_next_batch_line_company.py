"""Next batch: document line items denormalize company_id from parent."""

from decimal import Decimal

import pytest

from sales.models import SalesItem
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_sales_invoice_line_has_company_id(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data

    item = SalesItem.objects.get(invoice_id=inv["id"])
    assert item.company_id == tenant_a.company.id
    assert item.quantity == Decimal("2")
