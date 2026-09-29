"""PJ-TRADER-OWNER — a small B2B trader's normal day.

Buy from a supplier, sell to a GSTIN customer on credit, receive part payment,
run the ledger + a GST worksheet, and confirm the books stay consistent.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from core.invariants import assert_all_invariants
from core.models import AuditEvent
from sales.models import SalesInvoice
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_trader_owner_normal_day():
    ns = seed_archetype("trader")
    company, oc = ns.company, ns.owner_client
    product = ns.products[1]  # a non-batch line
    supplier = ns.suppliers[0]
    customer = next(c for c in ns.customers if c.gstin)

    # 1. purchase 20 units
    pur = oc.post(
        "/api/v1/purchases/invoices/",
        {"supplier": supplier.id, "purchase_type": "GST",
         "items": [{"product": product.id, "quantity": "20", "unit_price": "50.00", "gst_rate": "18"}]},
        format="json",
    )
    assert pur.status_code == 201, pur.data
    assert oc.post(f"/api/v1/purchases/invoices/{pur.data['id']}/complete/").status_code == 200

    # 2. sell 8 on credit
    inv = oc.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "invoice_type": "GST",
         "items": [{"product": product.id, "quantity": "8", "unit_price": "100.00", "gst_rate": "18"}]},
        format="json",
    )
    assert inv.status_code == 201, inv.data
    done = oc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/")
    assert done.status_code == 200, done.data
    grand = Decimal(str(done.data["grand_total"]))  # 800 + 144 = 944

    # 3. receive a part payment and allocate it
    rec = oc.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "500.00", "method": "BANK",
         "allocations": [{"sales_invoice": inv.data["id"], "amount": "500.00"}]},
        format="json",
    )
    assert rec.status_code in (200, 201), rec.data

    # 4. owner runs the customer ledger + GSTR-1 aid
    led = oc.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert led.status_code == 200, led.data
    assert oc.get(f"/api/v1/reports/gstr1/?period={done.data['invoice_date'][:7]}").status_code == 200

    # 5. stock moved: 20 in, 8 out -> 12
    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("12.000")

    assert_all_invariants(company)


def test_pj_trader_gst_guard_override_capability_boundary():
    """PJ-TRADER-GST-GUARD — GST Guard's OWNER/MANAGER override boundary.

    A B2B GST invoice missing its HSN code is a blocking GstGuardBlocked issue
    (reporting.gst_guard.validate_document -> HSN_MISSING). OWNER can override
    it with a reason, leaving a permanent AuditEvent; SALES_STAFF cannot, even
    with the same reason supplied.

    `fixtures.seed_archetype` never seeds a MANAGER-role persona (only OWNER,
    SALES_STAFF, ACCOUNTANT, VIEWER, and an import-capable SALES_STAFF — see
    fixtures.py), so a MANAGER membership is created ad hoc here, mirroring
    the same one-off pattern `tests/test_gst_guard_v2.py::_make_membership_client`
    already uses for this exact boundary.
    """
    ns = seed_archetype("trader")
    company = ns.company
    company.feature_flags = {"ENABLE_GST_GUARD": True}
    company.save(update_fields=["feature_flags"])

    customer = next(c for c in ns.customers if c.gstin)  # B2B -> HSN is mandatory
    product = next(p for p in ns.products if not p.track_batch)
    product.hsn_code = ""
    product.save(update_fields=["hsn_code"])

    from inventory.models import MovementType
    from inventory.services import InventoryService

    InventoryService.post_movement(
        company=company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"), unit_cost=Decimal("60.00"), user=ns.owner,
    )

    today_str = timezone.localdate().isoformat()

    def _draft(client):
        r = client.post(
            "/api/v1/sales/invoices/",
            {"customer": customer.id, "invoice_type": "GST", "invoice_date": today_str,
             "items": [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}]},
            format="json",
        )
        assert r.status_code == 201, r.data
        return r.data["id"]

    # 1. Owner drafts; a bare Complete (no override) is blocked for everyone,
    #    owner included -- the guard is not an owner-only speed bump.
    owner_inv_id = _draft(ns.owner_client)
    bare = ns.owner_client.post(f"/api/v1/sales/invoices/{owner_inv_id}/complete/")
    assert bare.status_code == 400, bare.data
    err = bare.data.get("error") or bare.data
    assert err.get("code") == "gst_guard_blocked"
    assert SalesInvoice.objects.get(pk=owner_inv_id).status == SalesInvoice.Status.DRAFT

    # 2. Owner supplies an override reason -> allowed, and it leaves a permanent
    #    audit trail naming the overridden issue.
    override = ns.owner_client.post(
        f"/api/v1/sales/invoices/{owner_inv_id}/complete/",
        {"gst_guard_override_reason": "Owner confirmed HSN with supplier invoice"},
        format="json",
    )
    assert override.status_code == 200, override.data
    owner_invoice = SalesInvoice.objects.get(pk=owner_inv_id)
    assert owner_invoice.status == SalesInvoice.Status.COMPLETED
    assert owner_invoice.gst_guard_override_reason == "Owner confirmed HSN with supplier invoice"
    assert owner_invoice.gst_guard_overridden_by_id is not None
    assert AuditEvent.objects.filter(
        company=company, entity_type="SalesInvoice", entity_id=str(owner_invoice.pk),
        description__icontains="GST Guard override",
    ).exists()

    # 3. A MANAGER persona (ad hoc -- not part of the seeded role set) gets the
    #    same override capability as OWNER.
    manager_user = User.objects.create_user(
        email="manager@trader.persona.test", password="StrongPass123!", full_name="trader-manager",
    )
    manager_cu = CompanyUser(company=company, user=manager_user, role=CompanyUser.Role.MANAGER)
    for k, v in CompanyUser.capability_defaults_for_role(CompanyUser.Role.MANAGER).items():
        setattr(manager_cu, k, v)
    manager_cu.save()
    manager_client = APIClient()
    manager_client.force_authenticate(user=manager_user)

    manager_inv_id = _draft(manager_client)
    manager_override = manager_client.post(
        f"/api/v1/sales/invoices/{manager_inv_id}/complete/",
        {"gst_guard_override_reason": "Manager approved"},
        format="json",
    )
    assert manager_override.status_code == 200, manager_override.data
    assert SalesInvoice.objects.get(pk=manager_inv_id).status == SalesInvoice.Status.COMPLETED

    # 4. SALES_STAFF drafts the same kind of invoice; supplying the same
    #    override reason is still rejected -- override is OWNER/MANAGER only.
    sales_inv_id = _draft(ns.sales_client)
    sales_denied = ns.sales_client.post(
        f"/api/v1/sales/invoices/{sales_inv_id}/complete/",
        {"gst_guard_override_reason": "I promise it's fine"},
        format="json",
    )
    assert sales_denied.status_code == 400, sales_denied.data
    sales_err = sales_denied.data.get("error") or sales_denied.data
    assert sales_err.get("code") == "gst_guard_blocked"
    assert SalesInvoice.objects.get(pk=sales_inv_id).status == SalesInvoice.Status.DRAFT
    assert SalesInvoice.objects.get(pk=sales_inv_id).gst_guard_overridden_by_id is None

    assert_all_invariants(company)
