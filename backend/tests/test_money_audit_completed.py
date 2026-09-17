"""Completed-document money edits must write MoneyFieldAudit (H-audit ⛔ close).

Line-price amends recompute grand_total inside set_items; the serializer used
to log only fields present in validated_data, so a price amend could skip the
money trail even though AuditEvent fired.
"""

from decimal import Decimal

import pytest

from core.models import MoneyFieldAudit
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_completed_sale_line_amend_writes_money_field_audit(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    before = Decimal(str(done.data["grand_total"]))

    resp = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": done.data.get("amend_revision", 0),
            "items": [{"product": product.id, "quantity": "2", "unit_price": "90"}],
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    after = Decimal(str(resp.data["grand_total"]))
    assert after != before

    rows = MoneyFieldAudit.objects.filter(
        company=tenant_a.company,
        entity_type="salesinvoice",
        entity_id=inv["id"],
        field="grand_total",
    )
    assert rows.exists(), "completed sale price amend must write MoneyFieldAudit for grand_total"
    latest = rows.latest("id")
    assert Decimal(latest.old_value) == before
    assert Decimal(latest.new_value) == after


def test_completed_purchase_line_amend_writes_money_field_audit(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "5", "unit_price": "80"}],
    )
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert done.status_code == 200, done.data
    before = Decimal(str(done.data["grand_total"]))

    resp = tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{pur['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "5", "unit_price": "70"}],
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    after = Decimal(str(resp.data["grand_total"]))
    assert after != before

    rows = MoneyFieldAudit.objects.filter(
        company=tenant_a.company,
        entity_type="purchaseinvoice",
        entity_id=pur["id"],
        field="grand_total",
    )
    assert rows.exists(), "completed purchase price amend must write MoneyFieldAudit for grand_total"
    latest = rows.latest("id")
    assert Decimal(latest.old_value) == before
    assert Decimal(latest.new_value) == after
