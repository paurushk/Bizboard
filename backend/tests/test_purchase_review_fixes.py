"""Purchase review WP-2 / WP-4 / WP-5: cancel with payments, detail context, GRN safeguards, orphan report."""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from inventory.models import StockMovement
from payments.models import PaymentAllocation, SupplierPayment
from purchases.models import GoodsReceipt, PurchaseInvoice
from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db

BASE = "/api/v1/purchases/invoices"
GRN = "/api/v1/purchases/grns"


def _paid_bill(tenant, price="100", paid="40"):
    supplier = make_supplier(tenant.company)
    product = make_product(tenant.company, sku=f"RF-{price}-{paid}")
    draft = create_draft_purchase(
        tenant,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": price, "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    resp = tenant.client.post(
        f"{BASE}/{draft['id']}/complete/", {"pay_now": {"amount": paid, "mode": "CASH"}}, format="json"
    )
    assert resp.status_code == 200 and resp.data["payment"], resp.data
    return supplier, product, draft


# ---- WP-2: cancel a bill that has payments --------------------------------------------------


def test_cancel_with_allocations_is_refused_with_a_structured_error(tenant_a):
    _, _, draft = _paid_bill(tenant_a)
    resp = tenant_a.client.post(f"{BASE}/{draft['id']}/cancel/")
    assert resp.status_code == 400
    body = resp.json()
    details = body.get("error", {}).get("details", {})
    assert details.get("allocatedTotal") == "40.00"
    assert len(details["allocations"]) == 1
    assert PurchaseInvoice.objects.get(pk=draft["id"]).status == "COMPLETED"


def test_cancel_with_reverse_allocations_keeps_the_payment_as_supplier_advance(tenant_a):
    _, _, draft = _paid_bill(tenant_a)
    resp = tenant_a.client.post(f"{BASE}/{draft['id']}/cancel/", {"reverse_allocations": True}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "CANCELLED"
    pay = SupplierPayment.objects.get()
    assert pay.status == "POSTED"  # the money movement is untouched
    assert not PaymentAllocation.objects.filter(purchase_invoice_id=draft["id"], reversed_at__isnull=True).exists()
    assert PaymentAllocation.objects.filter(purchase_invoice_id=draft["id"], reversed_at__isnull=False).count() == 1


def test_cancel_with_reverse_still_blocked_by_a_completed_return_and_changes_nothing(tenant_a):
    supplier, product, draft = _paid_bill(tenant_a)
    ret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": draft["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/").status_code == 200
    resp = tenant_a.client.post(f"{BASE}/{draft['id']}/cancel/", {"reverse_allocations": True}, format="json")
    assert resp.status_code == 400
    assert PaymentAllocation.objects.filter(purchase_invoice_id=draft["id"], reversed_at__isnull=True).count() == 1


# ---- WP-4: detail context ----------------------------------------------------------------


def test_retrieve_includes_payments_and_related_documents_but_list_does_not(tenant_a):
    _, _, draft = _paid_bill(tenant_a)
    detail = tenant_a.client.get(f"{BASE}/{draft['id']}/")
    assert detail.status_code == 200
    assert len(detail.data["payments"]) == 1
    assert Decimal(str(detail.data["payments"][0]["amount"])) == Decimal("40.00")
    assert set(detail.data["related_documents"]) == {
        "source_orders", "source_receipts", "returns", "credit_notes", "debit_notes",
    }
    listing = tenant_a.client.get(f"{BASE}/")
    assert listing.status_code == 200
    row = listing.data["results"][0] if isinstance(listing.data, dict) else listing.data[0]
    assert row["payments"] is None and row["related_documents"] is None


def test_retrieve_query_count_does_not_grow_with_payments(tenant_a, django_assert_max_num_queries):
    _, _, draft = _paid_bill(tenant_a)
    tenant_a.client.post(f"{BASE}/{draft['id']}/record-payment/", {"amount": "10", "mode": "CASH"}, format="json")
    tenant_a.client.post(f"{BASE}/{draft['id']}/record-payment/", {"amount": "10", "mode": "CASH"}, format="json")
    with django_assert_max_num_queries(60):
        assert tenant_a.client.get(f"{BASE}/{draft['id']}/").status_code == 200


# ---- WP-5: goods receipts --------------------------------------------------------------------


def _grn_payload(supplier, product, **extra):
    from inventory.services import InventoryService

    return {
        "supplier": supplier.id,
        "warehouse": InventoryService.default_warehouse(supplier.company).id,
        "items": [
            {
                "product": product.id,
                "quantity_received": "5",
                "quantity_accepted": "5",
                "quantity_rejected": "0",
                "unit_price": "10",
            }
        ],
        **extra,
    }


def test_grn_complete_with_same_key_posts_stock_once(tenant_a):
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="GRN-IDEM")
    created = tenant_a.client.post(GRN + "/", _grn_payload(supplier, product), format="json")
    assert created.status_code == 201, created.data
    url = f"{GRN}/{created.data['id']}/complete/"
    first = tenant_a.client.post(url, HTTP_IDEMPOTENCY_KEY="grn-k1")
    before = StockMovement.objects.count()
    second = tenant_a.client.post(url, HTTP_IDEMPOTENCY_KEY="grn-k1")
    assert first.status_code == 200 and second.status_code == 200
    assert StockMovement.objects.count() == before


def test_draft_grn_can_be_cancelled_but_a_completed_one_cannot_be_deleted(tenant_a):
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="GRN-CXL")
    draft = tenant_a.client.post(GRN + "/", _grn_payload(supplier, product), format="json").data
    cancelled = tenant_a.client.post(f"{GRN}/{draft['id']}/cancel/")
    assert cancelled.status_code == 200 and cancelled.data["status"] == "CANCELLED"
    other = tenant_a.client.post(GRN + "/", _grn_payload(supplier, product), format="json").data
    assert tenant_a.client.post(f"{GRN}/{other['id']}/complete/").status_code == 200
    assert tenant_a.client.delete(f"{GRN}/{other['id']}/").status_code == 400
    assert GoodsReceipt.objects.filter(pk=other["id"]).exists()


def test_grn_rejects_a_purchase_order_of_another_supplier_or_tenant(tenant_a, tenant_b):
    supplier = make_supplier(tenant_a.company)
    other_supplier = make_supplier(tenant_a.company, name="Other Supplier")
    product = make_product(tenant_a.company, sku="GRN-PO")
    order = tenant_a.client.post(
        "/api/v1/purchases/orders/",
        {
            "supplier": other_supplier.id,
            "purchase_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "5", "unit_price": "10", "gst_rate": "0"}],
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    mismatch = tenant_a.client.post(
        GRN + "/", _grn_payload(supplier, product, purchase_order=order.data["id"]), format="json"
    )
    assert mismatch.status_code == 400
    matching = tenant_a.client.post(
        GRN + "/", _grn_payload(other_supplier, product, purchase_order=order.data["id"]), format="json"
    )
    assert matching.status_code == 201, matching.data
    cross_tenant = tenant_b.client.post(
        GRN + "/", _grn_payload(make_supplier(tenant_b.company), make_product(tenant_b.company, sku="GRN-X"),
                                purchase_order=order.data["id"]),
        format="json",
    )
    assert cross_tenant.status_code == 400


# ---- orphan report ----------------------------------------------------------------------------


def test_orphan_report_lists_unallocated_against_payments_only(tenant_a, tmp_path):
    _paid_bill(tenant_a)  # its payment is fully allocated: must not be listed
    from payments.services import PaymentService

    supplier = make_supplier(tenant_a.company, name="Orphan Co")
    orphan = PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("25.00"), mode="CASH",
        notes="Against PUR-9", user=tenant_a.owner,
    )
    path = tmp_path / "orphans.csv"
    call_command("report_orphan_purchase_payments", company=tenant_a.company.id, csv=str(path), stderr=StringIO())
    text = path.read_text(encoding="utf8")
    rows = [line for line in text.splitlines() if line.strip()]
    assert len(rows) == 2, text  # header + the one orphan; the fully allocated payment is not listed
    assert orphan.number in rows[1]
