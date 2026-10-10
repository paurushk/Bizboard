from __future__ import annotations

from datetime import date
import pytest

from sales.models import Quotation
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


def test_quotation_filtering_search_and_dates(tenant_a):
    company = tenant_a.company
    cust1 = make_customer(company, name="Alpha Corp")
    cust2 = make_customer(company, name="Beta Industries")
    prod = make_product(company, selling_price="100.00")

    # Create 2 quotations with different dates
    q1_resp = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": cust1.id,
            "quotation_date": "2026-01-10",
            "valid_until": "2026-02-10",
            "items": [{"product": prod.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert q1_resp.status_code == 201, q1_resp.data
    q1_id = q1_resp.data["id"]

    q2_resp = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": cust2.id,
            "quotation_date": "2026-03-20",
            "valid_until": "2026-04-20",
            "items": [{"product": prod.id, "quantity": "10", "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert q2_resp.status_code == 201, q2_resp.data
    q2_id = q2_resp.data["id"]

    # Search by customer name 'Alpha'
    resp = tenant_a.client.get("/api/v1/sales/quotations/?q=Alpha")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.data["results"]]
    assert q1_id in ids
    assert q2_id not in ids

    # Search by customer name 'Beta'
    resp = tenant_a.client.get("/api/v1/sales/quotations/?q=Beta")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.data["results"]]
    assert q2_id in ids
    assert q1_id not in ids

    # Filter by date_from
    resp = tenant_a.client.get("/api/v1/sales/quotations/?date_from=2026-02-01")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.data["results"]]
    assert q2_id in ids
    assert q1_id not in ids

    # Filter by date_to
    resp = tenant_a.client.get("/api/v1/sales/quotations/?date_to=2026-02-01")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.data["results"]]
    assert q1_id in ids
    assert q2_id not in ids


def test_quotation_cancel_and_partially_converted_header_update(tenant_a):
    company = tenant_a.company
    cust = make_customer(company, name="Test Customer")
    prod = make_product(company, selling_price="50.00")

    # Create quotation
    q_resp = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": cust.id,
            "quotation_date": "2026-03-01",
            "valid_until": "2026-03-15",
            "items": [{"product": prod.id, "quantity": "10", "unit_price": "50.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert q_resp.status_code == 201, q_resp.data
    q_id = q_resp.data["id"]
    quotation = Quotation.objects.get(pk=q_id)

    # Cancel action
    cancel_resp = tenant_a.client.post(f"/api/v1/sales/quotations/{q_id}/cancel/")
    assert cancel_resp.status_code == 200
    quotation.refresh_from_db()
    assert quotation.status == Quotation.Status.CANCELLED

    # Create another quotation to test partial conversion and header update
    q2_resp = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": cust.id,
            "quotation_date": "2026-03-01",
            "valid_until": "2026-03-15",
            "items": [{"product": prod.id, "quantity": "10", "unit_price": "50.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert q2_resp.status_code == 201, q2_resp.data
    q2_id = q2_resp.data["id"]
    q2_item_id = q2_resp.data["items"][0]["id"]

    # Partially convert 4 units to order with confirm_expired=True
    conv_resp = tenant_a.client.post(
        f"/api/v1/sales/quotations/{q2_id}/convert-to-order/",
        {
            "items": [{"id": q2_item_id, "quantity": 4}],
            "confirm_expired": True,
        },
        format="json",
    )
    assert conv_resp.status_code == 200, conv_resp.data
    q2 = Quotation.objects.get(pk=q2_id)
    assert q2.status == Quotation.Status.DRAFT  # partial leaves in DRAFT

    # Update delivery address and valid_until without changing lines
    patch_resp = tenant_a.client.patch(
        f"/api/v1/sales/quotations/{q2_id}/",
        {
            "valid_until": "2026-03-30",
            "delivery_address": "123 Warehouse Rd",
        },
        format="json",
    )
    assert patch_resp.status_code == 200, patch_resp.data
    q2.refresh_from_db()
    assert q2.valid_until == date(2026, 3, 30)
    assert q2.delivery_address == "123 Warehouse Rd"
