"""ACT-01 on a real database: a failed payment leaves nothing behind, and the public page leaves no tenant context."""

from unittest import mock

import pytest
from django.db import connection
from rest_framework.test import APIClient

from core.exceptions import BusinessRuleError
from inventory.models import StockMovement
from payments.models import CustomerReceipt
from payments.services import PaymentService
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _draft(tenant, sku):
    product = make_product(tenant.company, sku=sku, hsn_code="3004", gst_rate="18")
    add_stock(tenant, product, "5")
    customer = make_customer(tenant.company, name="Atomic Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"},
    ])
    return draft["id"], customer


def test_failed_allocation_rolls_back_invoice_number_stock_and_receipt(tenant_a):
    invoice_id, customer = _draft(tenant_a, "ATOM-1")
    before = StockMovement.objects.filter(company=tenant_a.company).count()

    with mock.patch.object(PaymentService, "allocate_receipt", side_effect=BusinessRuleError("allocation refused")):
        res = tenant_a.client.post(
            f"/api/v1/sales/invoices/{invoice_id}/complete/",
            {"amount_received": "118", "payment_mode": "CASH"}, format="json",
        )
    assert res.status_code >= 400, res.data

    invoice = SalesInvoice.objects.get(pk=invoice_id)
    assert invoice.status == SalesInvoice.Status.DRAFT
    assert not (invoice.number or "").strip()
    assert StockMovement.objects.filter(company=tenant_a.company).count() == before
    assert not CustomerReceipt.objects.filter(customer=customer).exists()

    # The same bill completes cleanly afterwards, with one receipt that is fully allocated.
    ok = tenant_a.client.post(
        f"/api/v1/sales/invoices/{invoice_id}/complete/",
        {"amount_received": "118", "payment_mode": "CASH"}, format="json",
    )
    assert ok.status_code == 200, ok.data
    assert CustomerReceipt.objects.filter(customer=customer).count() == 1


def test_numbers_stay_consecutive_after_a_rolled_back_complete(tenant_a):
    first_id, _ = _draft(tenant_a, "ATOM-2")
    second_id, _ = _draft(tenant_a, "ATOM-3")
    with mock.patch.object(PaymentService, "allocate_receipt", side_effect=BusinessRuleError("nope")):
        tenant_a.client.post(
            f"/api/v1/sales/invoices/{first_id}/complete/",
            {"amount_received": "118", "payment_mode": "CASH"}, format="json",
        )
    a = tenant_a.client.post(f"/api/v1/sales/invoices/{second_id}/complete/")
    b = tenant_a.client.post(f"/api/v1/sales/invoices/{first_id}/complete/")
    assert a.status_code == 200 and b.status_code == 200
    na, nb = a.data["number"], b.data["number"]
    tail = lambda n: int("".join(ch for ch in n if ch.isdigit()) or 0)  # noqa: E731
    assert tail(nb) == tail(na) + 1, (na, nb)


@pytest.mark.postgres
@pytest.mark.skipif(connection.vendor != "postgresql", reason="Reads Postgres session settings")
def test_public_invoice_request_leaves_no_tenant_context_on_the_connection(tenant_a):
    invoice_id, _ = _draft(tenant_a, "ATOM-4")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/complete/").status_code == 200
    token = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/").data["url"].rsplit("/", 1)[-1]

    assert APIClient().get(f"/api/v1/public/invoices/{token}/").status_code == 200

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.company_id', true), current_setting('app.rls_bypass', true)")
        company_guc, bypass_guc = cursor.fetchone()
    assert not company_guc, f"company context leaked onto the connection: {company_guc!r}"
    assert bypass_guc in (None, "", "0"), f"RLS bypass leaked onto the connection: {bypass_guc!r}"
