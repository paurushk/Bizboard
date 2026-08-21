"""Tenant isolation — every query scoped by company_id (§3.1.8, E7.5)."""

import pytest

from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_customers_are_isolated(tenant_a, tenant_b):
    make_customer(tenant_a.company, name="Alpha Customer")
    resp = tenant_b.client.get("/api/v1/customers/")
    assert resp.status_code == 200
    assert resp.data["count"] == 0


def test_cannot_retrieve_other_companys_invoice(tenant_a, tenant_b):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    resp = tenant_b.client.get(f"/api/v1/sales/invoices/{inv['id']}/")
    assert resp.status_code == 404


def test_cannot_use_other_companys_product_or_customer(tenant_a, tenant_b):
    product_a = make_product(tenant_a.company)
    customer_b = make_customer(tenant_b.company)
    resp = tenant_b.client.post("/api/v1/sales/invoices/", {
        "customer": customer_b.id,
        "items": [{"product": product_a.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400

    customer_a = make_customer(tenant_a.company)
    product_b = make_product(tenant_b.company)
    resp = tenant_b.client.post("/api/v1/sales/invoices/", {
        "customer": customer_a.id,
        "items": [{"product": product_b.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_stock_balances_are_isolated(tenant_a, tenant_b):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    resp = tenant_b.client.get("/api/v1/inventory/balances/")
    assert resp.data["count"] == 0


def test_ledger_access_is_isolated(tenant_a, tenant_b):
    customer = make_customer(tenant_a.company)
    resp = tenant_b.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert resp.status_code == 404


def test_document_numbers_are_per_company(tenant_a, tenant_b):
    for tenant in (tenant_a, tenant_b):
        product = make_product(tenant.company)
        add_stock(tenant, product, "10")
        customer = make_customer(tenant.company)
        inv = create_draft_invoice(tenant, customer, [
            {"product": product.id, "quantity": "1", "unit_price": "100"}
        ])
        resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
        # Both companies get INV-00001 — sequences are independent
        assert resp.data["number"] == "INV-00001"


def test_search_is_isolated(tenant_a, tenant_b):
    make_customer(tenant_a.company, name="UniqueAlphaName")
    resp = tenant_b.client.get("/api/v1/search/", {"q": "UniqueAlphaName"})
    assert resp.data["customers"] == []


def test_unauthenticated_requests_rejected():
    from rest_framework.test import APIClient

    resp = APIClient().get("/api/v1/customers/")
    assert resp.status_code == 401


def test_receipt_for_other_companys_customer_rejected(tenant_a, tenant_b):
    customer_a = make_customer(tenant_a.company)
    resp = tenant_b.client.post("/api/v1/payments/receipts/", {
        "customer": customer_a.id, "amount": "100", "mode": "CASH",
    }, format="json")
    assert resp.status_code == 400


def test_cross_tenant_write_attempts_all_rejected(tenant_a, tenant_b):
    """BUG-721 — every mutating endpoint (PATCH/DELETE/action) must reject a
    request scoped to another tenant's object id with 404, not just GET/create.
    IDs are sequential BigAutoFields across the whole system, so this is a
    realistic, cheap cross-tenant attack surface to leave untested."""
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    invoice = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    purchase = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "1", "unit_price": "80"}
    ])

    cases = [
        ("patch", f"/api/v1/sales/invoices/{invoice['id']}/", {"invoice_discount": "5"}),
        ("delete", f"/api/v1/sales/invoices/{invoice['id']}/", None),
        ("post", f"/api/v1/sales/invoices/{invoice['id']}/complete/", None),
        ("post", f"/api/v1/sales/invoices/{invoice['id']}/cancel/", None),
        ("post", f"/api/v1/sales/invoices/{invoice['id']}/regenerate-pdf/", None),
        ("post", f"/api/v1/sales/invoices/{invoice['id']}/share/", {"channel": "email"}),
        ("patch", f"/api/v1/purchases/invoices/{purchase['id']}/", {"invoice_discount": "5"}),
        ("delete", f"/api/v1/purchases/invoices/{purchase['id']}/", None),
        ("post", f"/api/v1/purchases/invoices/{purchase['id']}/complete/", None),
        ("post", f"/api/v1/purchases/invoices/{purchase['id']}/cancel/", None),
        ("patch", f"/api/v1/customers/{customer.id}/", {"name": "Hijacked"}),
        ("delete", f"/api/v1/customers/{customer.id}/", None),
        ("patch", f"/api/v1/suppliers/{supplier.id}/", {"name": "Hijacked"}),
        ("delete", f"/api/v1/suppliers/{supplier.id}/", None),
        ("patch", f"/api/v1/products/{product.id}/", {"name": "Hijacked"}),
        ("delete", f"/api/v1/products/{product.id}/", None),
    ]
    for method, path, payload in cases:
        call = getattr(tenant_b.client, method)
        resp = call(path, payload, format="json") if payload is not None else call(path)
        assert resp.status_code == 404, f"{method.upper()} {path} returned {resp.status_code}, expected 404"


def test_cross_tenant_invoice_patch_and_delete_rejected(tenant_a, tenant_b):
    """P0-109 / BUG-721 — focused PATCH/DELETE of another tenant's invoice → 404."""
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    invoice = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])

    patch = tenant_b.client.patch(
        f"/api/v1/sales/invoices/{invoice['id']}/",
        {"invoice_discount": "5"},
        format="json",
    )
    assert patch.status_code == 404

    delete = tenant_b.client.delete(f"/api/v1/sales/invoices/{invoice['id']}/")
    assert delete.status_code == 404

    # Own-tenant invoice still intact.
    own = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice['id']}/")
    assert own.status_code == 200
    assert own.data["id"] == invoice["id"]


def test_cross_tenant_purchase_phase1_fk_rejected(tenant_a, tenant_b):
    """Purchase CN/DN/PO must not accept another tenant's supplier/invoice FKs."""
    product_a = make_product(tenant_a.company, sku="TA-P1")
    supplier_a = make_supplier(tenant_a.company, name="Alpha Supplier")
    product_b = make_product(tenant_b.company, sku="TB-P1")
    add_stock(tenant_b, product_b, "5")

    cases = [
        (
            "/api/v1/purchases/credit-notes/",
            {
                "supplier": supplier_a.id,
                "reason": "CORRECTION_OF_INVOICE",
                "items": [
                    {"product": product_b.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}
                ],
            },
        ),
        (
            "/api/v1/purchases/debit-notes/",
            {
                "supplier": supplier_a.id,
                "reason": "CORRECTION_OF_INVOICE",
                "items": [
                    {"product": product_b.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}
                ],
            },
        ),
        (
            "/api/v1/purchases/orders/",
            {
                "supplier": supplier_a.id,
                "purchase_type": "NON_GST",
                "items": [
                    {"product": product_b.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}
                ],
            },
        ),
    ]
    for path, payload in cases:
        resp = tenant_b.client.post(path, payload, format="json")
        assert resp.status_code == 400, f"{path} returned {resp.status_code}: {resp.data}"
        assert "supplier" in resp.data or "Invalid reference" in str(resp.data)


def test_cannot_mass_assign_company_on_invoice_or_customer(tenant_a, tenant_b):
    """BB-000084: PATCH/POST must ignore client-supplied company / company_id."""
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Keep Tenant")
    invoice = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])

    patch_customer = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/",
        {"company": tenant_b.company.id, "company_id": tenant_b.company.id, "name": "Still Alpha"},
        format="json",
    )
    assert patch_customer.status_code == 200, patch_customer.data
    customer.refresh_from_db()
    assert customer.company_id == tenant_a.company.id
    assert customer.name == "Still Alpha"

    create_customer = tenant_a.client.post(
        "/api/v1/customers/",
        {
            "name": "New Party",
            "state": "Karnataka",
            "company": tenant_b.company.id,
            "company_id": tenant_b.company.id,
        },
        format="json",
    )
    assert create_customer.status_code == 201, create_customer.data
    from masters.models import Customer

    created = Customer.objects.get(pk=create_customer.data["id"])
    assert created.company_id == tenant_a.company.id

    patch_invoice = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{invoice['id']}/",
        {"company": tenant_b.company.id, "company_id": tenant_b.company.id, "notes": "no spoof"},
        format="json",
    )
    assert patch_invoice.status_code == 200, patch_invoice.data
    from sales.models import SalesInvoice

    inv = SalesInvoice.objects.get(pk=invoice["id"])
    assert inv.company_id == tenant_a.company.id
    assert inv.notes == "no spoof"

    membership = tenant_a.company.memberships.filter(user=tenant_a.staff).first()
    assert membership is not None
    patch_user = tenant_a.client.patch(
        f"/api/v1/company/users/{membership.id}/",
        {"company": tenant_b.company.id, "company_id": tenant_b.company.id},
        format="json",
    )
    assert patch_user.status_code == 200, patch_user.data
    membership.refresh_from_db()
    assert membership.company_id == tenant_a.company.id


def test_journal_and_allocation_viewsets_are_company_scoped(tenant_a, tenant_b):
    """BB-000085: non-legacy ViewSets that touch company data still filter by tenant."""
    from accounting.models import JournalEntry, JournalLine
    from accounting.services import seed_chart_of_accounts
    from payments.models import PaymentAllocation
    from payments.services import PaymentService

    for tenant in (tenant_a, tenant_b):
        tenant.company.accounting_enabled = True
        tenant.company.save(update_fields=["accounting_enabled"])
        seed_chart_of_accounts(tenant.company, tenant.owner)

    from accounting.services import PostingService

    cash_a = PostingService._account(tenant_a.company, "1100")
    equity_a = PostingService._account(tenant_a.company, "3100")
    entry = JournalEntry.objects.create(
        company=tenant_a.company,
        status=JournalEntry.Status.DRAFT,
        entry_date="2026-04-01",
        narration="tenant-a only",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    JournalLine.objects.create(
        company=tenant_a.company, entry=entry, account=cash_a, debit="50.00", credit="0",
    )
    JournalLine.objects.create(
        company=tenant_a.company, entry=entry, account=equity_a, debit="0", credit="50.00",
    )

    assert tenant_b.client.get(f"/api/v1/accounting/journals/{entry.id}/").status_code == 404
    listed = tenant_b.client.get("/api/v1/accounting/journals/")
    assert listed.status_code == 200
    assert all(row["id"] != entry.id for row in listed.data.get("results", listed.data))

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    invoice = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice['id']}/complete/")
    assert completed.status_code == 200, completed.data
    receipt = PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=completed.data["grand_total"], mode="CASH",
        user=tenant_a.owner,
    )
    from sales.models import SalesInvoice

    inv = SalesInvoice.objects.get(pk=completed.data["id"])
    allocation = PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=inv, amount=inv.grand_total, user=tenant_a.owner,
    )
    assert tenant_b.client.get(f"/api/v1/payments/allocations/{allocation.id}/").status_code == 404
    assert PaymentAllocation.objects.filter(pk=allocation.id, company=tenant_a.company).exists()

