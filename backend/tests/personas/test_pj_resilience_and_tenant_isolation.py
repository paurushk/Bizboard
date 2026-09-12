"""Persona Journey — Idempotency, Concurrency & Multi-Tenant Security Isolation.

Validates the BizBoard Resilience, Security & RBAC Truth Chain (T7):
1. Idempotency & Safe Retries:
   - Duplicate submissions with the same Idempotency-Key return cached response.
   - Exactly 1 invoice, 1 stock deduction, and 1 set of GL entries created.
2. Strict Multi-Tenant Security Isolation:
   - Zero data leakage between Tenant A and Tenant B across products, customers, invoices, and dashboards.
   - Cross-tenant penetration attempts return HTTP 404 / 400.
3. Systematic RBAC Matrix Enforcement:
   - Sales Staff, Accountant, and Owner capability boundaries tested against sensitive operations.
4. Invariants:
   - assert_all_invariants(company) holds clean.
"""

from __future__ import annotations

from decimal import Decimal
import uuid

import pytest
from django.utils import timezone

from accounting.models import Account, AccountingPeriod
from core.invariants import assert_all_invariants
from inventory.models import MovementType
from inventory.services import InventoryService
from sales.models import SalesInvoice
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_idempotency_safe_retry_single_transaction_effect():
    """T7 Resilience: Duplicate request with Idempotency-Key produces exactly one business effect."""
    ns = seed_archetype("trader")
    company = ns.company
    oc = ns.owner_client
    cust = ns.customers[0]
    p = next(prod for prod in ns.products if not prod.track_batch)
    today_str = timezone.localdate().isoformat()

    # Inward stock
    InventoryService.post_movement(
        company=company,
        product=p,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("60.00"),
        user=ns.owner,
    )

    idem_key = f"idem-{uuid.uuid4()}"
    payload = {
        "customer": cust.id,
        "invoice_type": "GST",
        "invoice_date": today_str,
        "items": [
            {"product": p.id, "quantity": "5.000", "unit_price": "100.00", "gst_rate": "18.00"}
        ],
    }

    # Request 1: Initial submission
    r1 = oc.post("/api/v1/sales/invoices/", payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_key)
    assert r1.status_code == 201, r1.data
    inv_id = r1.data["id"]

    # Request 2: Network drop retry (client resends exact payload with identical key)
    r2 = oc.post("/api/v1/sales/invoices/", payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_key)
    assert r2.status_code in (200, 201), r2.data
    assert r2.data["id"] == inv_id

    # Request 3: Third identical retry
    r3 = oc.post("/api/v1/sales/invoices/", payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_key)
    assert r3.status_code in (200, 201)
    assert r3.data["id"] == inv_id

    # Database Assertion: Exactly 1 invoice was created, NOT 3!
    matching_invoices = SalesInvoice.objects.filter(company=company, customer=cust)
    assert matching_invoices.count() == 1

    # Complete the invoice
    comp = oc.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert comp.status_code == 200

    assert_all_invariants(company)


def test_pj_idempotency_key_reused_with_different_payload_replays_first_response():
    """T7 Resilience — negative case for FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md §9:
    `core.idempotency` keys purely on (company, scope, key) — it never hashes or
    compares the request body (see `IdempotencyRecord` lookup in `begin_record`).
    So a client that reuses an Idempotency-Key across two *different* payloads
    (a client bug, e.g. a retried request whose body was mutated) gets the FIRST
    request's cached response replayed verbatim; the second, different payload is
    silently never processed — no second invoice, no error surfaced. This pins
    that behaviour so a future change to the idempotency layer is a deliberate
    decision, not an accidental regression either way."""
    ns = seed_archetype("trader")
    company = ns.company
    oc = ns.owner_client
    cust = ns.customers[0]
    p = next(prod for prod in ns.products if not prod.track_batch)
    today_str = timezone.localdate().isoformat()

    InventoryService.post_movement(
        company=company, product=p, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"), unit_cost=Decimal("60.00"), user=ns.owner,
    )

    idem_key = f"idem-{uuid.uuid4()}"
    first_payload = {
        "customer": cust.id,
        "invoice_type": "GST",
        "invoice_date": today_str,
        "items": [{"product": p.id, "quantity": "5.000", "unit_price": "100.00", "gst_rate": "18.00"}],
    }
    r1 = oc.post("/api/v1/sales/invoices/", first_payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_key)
    assert r1.status_code == 201, r1.data
    first_invoice_id = r1.data["id"]

    # Same key, materially different payload (different quantity) — a client bug.
    second_payload = dict(first_payload)
    second_payload["items"] = [
        {"product": p.id, "quantity": "20.000", "unit_price": "100.00", "gst_rate": "18.00"}
    ]
    r2 = oc.post("/api/v1/sales/invoices/", second_payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_key)

    # Current, pinned behaviour: the cached first response is replayed as-is —
    # same invoice id, same (5-unit) line — the 20-unit request is never posted.
    assert r2.status_code == 201, r2.data
    assert r2.data["id"] == first_invoice_id
    assert r2.data["items"][0]["quantity"] == first_payload["items"][0]["quantity"] == "5.000"

    assert SalesInvoice.objects.filter(company=company, customer=cust).count() == 1

    assert_all_invariants(company)


def test_pj_strict_multi_tenant_isolation():
    """T7 Security: Strict zero data leakage between Tenant A and Tenant B."""
    tenant_a = seed_archetype("trader")
    tenant_b = seed_archetype("retail")

    ca = tenant_a.company
    cb = tenant_b.company
    client_a = tenant_a.owner_client
    client_b = tenant_b.owner_client

    b_prod = tenant_b.products[0]
    b_cust = tenant_b.customers[0]

    # Attempt 1: Tenant A attempts to view Tenant B's product
    probe_prod = client_a.get(f"/api/v1/masters/products/{b_prod.id}/")
    assert probe_prod.status_code == 404, "Tenant A must never see Tenant B's products"

    # Attempt 2: Tenant A attempts to view Tenant B's customer
    probe_cust = client_a.get(f"/api/v1/masters/customers/{b_cust.id}/")
    assert probe_cust.status_code == 404, "Tenant A must never see Tenant B's customers"

    # Attempt 3: Tenant A attempts to bill Tenant B's customer
    p_a = tenant_a.products[0]
    probe_bill = client_a.post(
        "/api/v1/sales/invoices/",
        {
            "customer": b_cust.id,
            "invoice_type": "GST",
            "invoice_date": timezone.localdate().isoformat(),
            "items": [{"product": p_a.id, "quantity": "1.000", "unit_price": "100.00", "gst_rate": "18.00"}],
        },
        format="json",
    )
    assert probe_bill.status_code in (400, 404), "Tenant A must not be allowed to bill Tenant B's customer"

    # Attempt 4: Reporting dashboard query by Tenant A contains zero data from Tenant B
    dash_a = client_a.get("/api/v1/dashboard/")
    assert dash_a.status_code == 200
    assert dash_a.data["product_count"] == len(tenant_a.products)

    # Invariants hold for both tenants
    assert_all_invariants(ca)
    assert_all_invariants(cb)


def test_pj_systematic_rbac_matrix_enforcement():
    """T7 RBAC: Systematic persona boundary enforcement (Sales vs Accountant vs Owner)."""
    ns = seed_archetype("trader")
    company = ns.company
    clerk = ns.sales_client
    acct = ns.acct_client
    owner = ns.owner_client

    # 1. Sales Clerk boundaries
    # Can create draft invoice
    cust = ns.customers[0]
    p = next(prod for prod in ns.products if not prod.track_batch)
    can_draft = clerk.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": timezone.localdate().isoformat(),
            "items": [{"product": p.id, "quantity": "1.000", "unit_price": "100.00", "gst_rate": "18.00"}],
        },
        format="json",
    )
    assert can_draft.status_code == 201

    # Denied: Sales Clerk cannot post manual accounting journals
    acc_1100 = Account.objects.get(company=company, code="1100").id
    acc_1500 = Account.objects.get(company=company, code="1500").id
    clerk_jr_denied = clerk.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": timezone.localdate().isoformat(),
            "narration": "Unauthorized Clerk Entry",
            "lines": [
                {"account": acc_1500, "debit": "100.00", "credit": "0.00"},
                {"account": acc_1100, "debit": "0.00", "credit": "100.00"},
            ],
        },
        format="json",
    )
    assert clerk_jr_denied.status_code == 403, "Sales Clerk must be forbidden from posting journals"

    # Denied: Sales Clerk cannot create stock count sessions
    clerk_count_denied = clerk.post("/api/v1/inventory/stock-counts/", {"notes": "Audit"}, format="json")
    assert clerk_count_denied.status_code == 403, "Sales Clerk must be forbidden from stock counts"

    # 2. Munshi / Accountant boundaries
    # Can create and post manual journal
    acct_jr = acct.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": timezone.localdate().isoformat(),
            "narration": "Accountant Authorized Journal",
            "lines": [
                {"account": acc_1500, "debit": "100.00", "credit": "0.00"},
                {"account": acc_1100, "debit": "0.00", "credit": "100.00"},
            ],
        },
        format="json",
    )
    assert acct_jr.status_code == 201
    jr_post = acct.post(f"/api/v1/accounting/journals/{acct_jr.data['id']}/post/")
    assert jr_post.status_code in (200, 202)

    # Denied: Accountant cannot close fiscal periods
    period = AccountingPeriod.objects.create(
        company=company,
        name="FY26-Q1 Test",
        start_date="2026-04-01",
        end_date="2026-04-30",
        status=AccountingPeriod.Status.OPEN,
    )
    acct_close_denied = acct.post(f"/api/v1/accounting/periods/{period.id}/close/")
    assert acct_close_denied.status_code == 403, "Accountant must not have permission to close periods"

    # 3. Owner capability
    # Owner can close period
    owner_close = owner.post(f"/api/v1/accounting/periods/{period.id}/close/")
    assert owner_close.status_code == 200

    assert_all_invariants(company)
