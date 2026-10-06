"""Open sales defects from BUGS_REMEDIATION_PLAN.md (014, 003, 004, 006, 019, 020, 021)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from payments.models import CustomerPortalToken, CustomerReceipt, PaymentAllocation
from sales.models import (
    DeliveryRoute,
    DeliveryRouteStop,
    RouteCashHandover,
    SalesCreditNote,
    SalesCreditNoteItem,
    SalesInvoice,
    SalesItem,
    SalesOrder,
    SalesOrderItem,
)
from sales.route_service import RouteService
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _ids(resp):
    assert resp.status_code == 200, resp.data
    return {row["id"] for row in resp.data["results"]}


def _detail(resp):
    error = resp.data.get("error") or {}
    return str(error.get("details") or error.get("message") or resp.data)


def _posted_invoice(company, customer, total):
    return SalesInvoice.objects.create(
        company=company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=timezone.localdate(),
        grand_total=Decimal(total),
        taxable_total=Decimal(total),
    )


def test_bug_sales_014_paid_filter_ignores_reversed_receipts_and_counts_credit_notes(tenant_a):
    customer = make_customer(tenant_a.company, name="Paid Filter")
    voided = _posted_invoice(tenant_a.company, customer, "100")
    relieved = _posted_invoice(tenant_a.company, customer, "80")
    half_note = _posted_invoice(tenant_a.company, customer, "90")
    collected = _posted_invoice(tenant_a.company, customer, "70")

    void_receipt = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("100"),
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company,
        receipt=void_receipt,
        sales_invoice=voided,
        amount=Decimal("100"),
        reversed_at=timezone.now(),
    )
    live_receipt = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("70"),
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company,
        receipt=live_receipt,
        sales_invoice=collected,
        amount=Decimal("70"),
    )
    SalesCreditNote.objects.create(
        company=tenant_a.company,
        customer=customer,
        sales_invoice=relieved,
        status=SalesCreditNote.Status.COMPLETED,
        grand_total=Decimal("80"),
    )
    SalesCreditNote.objects.create(
        company=tenant_a.company,
        customer=customer,
        sales_invoice=half_note,
        status=SalesCreditNote.Status.COMPLETED,
        grand_total=Decimal("40"),
    )

    paid = _ids(tenant_a.client.get("/api/v1/sales/invoices/", {"payment_status": "PAID"}))
    partial = _ids(tenant_a.client.get("/api/v1/sales/invoices/", {"payment_status": "PARTIAL"}))
    unpaid = _ids(tenant_a.client.get("/api/v1/sales/invoices/", {"payment_status": "UNPAID"}))

    assert voided.id not in paid
    assert voided.id in unpaid
    assert relieved.id in paid
    assert relieved.id not in unpaid
    assert collected.id in paid
    assert half_note.id in partial
    assert half_note.id not in unpaid

    stats = tenant_a.client.get("/api/v1/sales/invoices/payment-stats/")
    assert stats.status_code == 200, stats.data
    assert int(stats.data["unpaid"]["count"]) >= 1
    assert int(stats.data["paid"]["count"]) >= 2
    assert int(stats.data["partial"]["count"]) >= 1


def _route(tenant, customer):
    product = make_product(tenant.company, sku=f"RT-{customer.id}", purchase_price="10", selling_price="20")
    order = SalesOrder.objects.create(company=tenant.company, customer=customer)
    SalesOrderItem.objects.create(
        company=tenant.company, sales_order=order, product=product, quantity=1, unit_price=20,
    )
    route = DeliveryRoute.objects.create(
        company=tenant.company, route_date="2026-10-04", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    stop = DeliveryRouteStop.objects.create(company=tenant.company, route=route, sales_order=order)
    return route, stop


def test_bug_sales_003_driver_collections_reconcile_to_the_drawer_without_posting_cash(tenant_a):
    customer = make_customer(tenant_a.company, name="Route Cash")
    route, stop = _route(tenant_a, customer)
    RouteService.set_stop_status(
        route, stop, "DELIVERED", tenant_a.owner,
        received_by_name="Ravi",
        collected_cash="200",
        collected_upi="50",
        upi_reference="UPI-ROUTE-1",
    )
    before = CustomerReceipt.objects.filter(company=tenant_a.company).count()
    refused = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/complete/", {}, format="json")
    assert refused.status_code == 400
    assert "cashier" in _detail(refused).lower()
    route.refresh_from_db()
    assert route.status == DeliveryRoute.Status.IN_TRANSIT

    short = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/verify-handover/",
        {"cash_counted": "180.00", "upi_counted": "50.00"},
        format="json",
    )
    assert short.status_code == 200, short.data
    handover = RouteCashHandover.objects.get(route=route)
    assert handover.status == RouteCashHandover.Status.VARIANCE
    assert handover.variance_amount == Decimal("-20.00")
    assert handover.expected_cash == Decimal("200.00")
    assert handover.counted_cash == Decimal("180.00")
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == before

    closed = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/complete/", {}, format="json")
    assert closed.status_code == 200, closed.data
    assert closed.data["status"] == "COMPLETED"
    assert closed.data["cash_handover"]["status"] == "VARIANCE"
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == before

    other = make_customer(tenant_a.company, name="Route Match")
    matched, matched_stop = _route(tenant_a, other)
    RouteService.set_stop_status(
        matched, matched_stop, "DELIVERED", tenant_a.owner,
        received_by_name="Ravi", collected_cash="10",
    )
    exact = RouteService.verify_cashier_handover(
        matched, tenant_a.owner, cash_counted="10", upi_counted="0",
    )
    assert exact.status == RouteCashHandover.Status.VERIFIED
    assert exact.variance_amount == Decimal("0.00")
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == before
    done = RouteService.complete_route(matched, tenant_a.owner)
    assert done.status == DeliveryRoute.Status.COMPLETED


def test_bug_sales_004_pod_refuses_an_arbitrary_otp(tenant_a):
    customer = make_customer(tenant_a.company, name="POD")
    route, stop = _route(tenant_a, customer)
    code = RouteService.issue_delivery_otp(route, stop, tenant_a.owner)
    stop.refresh_from_db()
    assert stop.otp_code == ""
    assert stop.delivery_otp_hash

    wrong = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {"stop_id": stop.id, "status": "DELIVERED", "received_by_name": "Ravi", "otp": "000000"},
        format="json",
    )
    assert wrong.status_code == 400
    assert "otp" in _detail(wrong).lower()
    stop.refresh_from_db()
    assert stop.status == DeliveryRouteStop.StopStatus.PENDING
    assert stop.otp_code == ""

    bare = DeliveryRouteStop.objects.create(
        company=tenant_a.company,
        route=route,
        sales_order=SalesOrder.objects.create(company=tenant_a.company, customer=customer),
    )
    arbitrary = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {"stop_id": bare.id, "status": "DELIVERED", "received_by_name": "Ravi", "otp": "123456"},
        format="json",
    )
    assert arbitrary.status_code == 400
    assert "otp" in _detail(arbitrary).lower()

    ok = RouteService.set_stop_status(
        route, stop, "DELIVERED", tenant_a.owner, received_by_name="Ravi", otp_code=code,
    )
    assert ok.status == DeliveryRouteStop.StopStatus.DELIVERED


def test_bug_sales_006_below_cost_blocks_complete_unless_the_company_allows_it(tenant_a):
    # fixture tenants allow below-cost bills; this test is about the block itself
    tenant_a.company.feature_flags = {**(tenant_a.company.feature_flags or {}), "allow_below_cost_sales": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company, name="Margin")
    product = make_product(tenant_a.company, sku="BELOW-1", purchase_price="80", selling_price="80", gst_rate="0")
    add_stock(tenant_a, product, "5", unit_cost="80")
    below = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    refused = tenant_a.client.post(f"/api/v1/sales/invoices/{below['id']}/complete/")
    assert refused.status_code == 400
    assert "below purchase cost" in _detail(refused).lower()

    at_cost = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    allowed = tenant_a.client.post(f"/api/v1/sales/invoices/{at_cost['id']}/complete/")
    assert allowed.status_code == 200, allowed.data

    flags = dict(tenant_a.company.feature_flags or {})
    flags["allow_below_cost_sales"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    waived = tenant_a.client.post(f"/api/v1/sales/invoices/{below['id']}/complete/")
    assert waived.status_code == 200, waived.data


def _portal(company, customer, token):
    return CustomerPortalToken.objects.create(
        company=company,
        customer=customer,
        token=token,
        requested_via="EMAIL",
        expires_at=timezone.now() + timedelta(minutes=15),
    )


def test_bug_sales_019_portal_complaints_are_paginated(tenant_a):
    from complaints.models import Complaint

    customer = make_customer(tenant_a.company, name="Complainer")
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_CUSTOMER_PORTAL"] = True
    flags["ENABLE_COMPLAINTS"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    Complaint.objects.bulk_create([
        Complaint(
            company=tenant_a.company,
            customer=customer,
            category=Complaint.Category.DAMAGED,
            description=f"Box {i}",
        )
        for i in range(3)
    ])
    token = _portal(tenant_a.company, customer, "sales-019-token")
    anon = APIClient()
    first = anon.get(
        f"/api/v1/public/customer-portal/{token.token}/complaints/",
        {"page": 1, "page_size": 1},
    )
    second = anon.get(
        f"/api/v1/public/customer-portal/{token.token}/complaints/",
        {"page": 2, "page_size": 1},
    )
    assert first.status_code == 200, first.data
    assert first.data["count"] == 3
    assert first.data["page_size"] == 1
    assert len(first.data["complaints"]) == 1
    assert second.data["complaints"][0]["id"] != first.data["complaints"][0]["id"]
    capped = anon.get(
        f"/api/v1/public/customer-portal/{token.token}/complaints/",
        {"page_size": 100000},
    )
    assert capped.data["page_size"] == 250
    assert len(capped.data["complaints"]) <= 250


def test_bug_sales_020_portal_pdf_refuses_draft_and_cancelled(tenant_a, monkeypatch):
    customer = make_customer(tenant_a.company, name="PDF Buyer")
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_CUSTOMER_PORTAL"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    draft = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.DRAFT,
        grand_total=Decimal("10"),
    )
    cancelled = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.CANCELLED,
        grand_total=Decimal("10"), number="CNCL-1",
    )
    live = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        grand_total=Decimal("10"), number="LIVE-1",
    )
    token = _portal(tenant_a.company, customer, "sales-020-token")
    monkeypatch.setattr("sales.pdf.render_gst_tax_invoice", lambda invoice, copy="ORIGINAL": b"%PDF-1.4 portal")
    anon = APIClient()
    base = f"/api/v1/public/customer-portal/{token.token}/invoices"
    assert anon.get(f"{base}/{draft.id}/pdf/").status_code == 404
    assert anon.get(f"{base}/{cancelled.id}/pdf/").status_code == 404
    pdf = anon.get(f"{base}/{live.id}/pdf/")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_bug_sales_021_partial_return_consumes_the_named_line(tenant_a):
    customer = make_customer(tenant_a.company, name="Two Rates")
    product = make_product(tenant_a.company, sku="TWO-1", purchase_price="40", gst_rate="0")
    add_stock(tenant_a, product, "4", unit_cost="40")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [
            {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"},
            {"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "0"},
        ],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    cheap, dear = list(SalesItem.objects.filter(invoice_id=inv["id"]).order_by("id"))
    assert cheap.unit_price == Decimal("100")
    assert dear.unit_price == Decimal("200")

    missing = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "0"}],
        },
        format="json",
    )
    assert missing.status_code == 400
    assert "source_item" in _detail(missing).lower()

    created = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "200",
                "gst_rate": "0",
                "source_item": dear.id,
            }],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    done = tenant_a.client.post(f"/api/v1/sales/returns/{created.data['id']}/complete/")
    assert done.status_code == 200, done.data
    note_line = SalesCreditNoteItem.objects.get(credit_note__sales_return_id=created.data["id"])
    assert note_line.source_item_id == dear.id

    again = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "200",
                "gst_rate": "0",
                "source_item": dear.id,
            }],
        },
        format="json",
    )
    assert again.status_code == 201, again.data
    overflow = tenant_a.client.post(f"/api/v1/sales/returns/{again.data['id']}/complete/")
    assert overflow.status_code == 400
    assert "named invoice line" in _detail(overflow).lower()

    cheap_return = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "100",
                "gst_rate": "0",
                "source_item": cheap.id,
            }],
        },
        format="json",
    )
    assert cheap_return.status_code == 201, cheap_return.data
    cheap_done = tenant_a.client.post(f"/api/v1/sales/returns/{cheap_return.data['id']}/complete/")
    assert cheap_done.status_code == 200, cheap_done.data
    cheap_note = SalesCreditNoteItem.objects.get(credit_note__sales_return_id=cheap_return.data["id"])
    assert cheap_note.source_item_id == cheap.id
