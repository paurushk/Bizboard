"""Next Batch #5: ACCOUNTANT / VIEWER role capability defaults and gates."""

from accounts.models import CompanyUser
from rest_framework.test import APIClient

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product


def _demote_staff_to_viewer(tenant):
    """Flip tenant.staff to VIEWER with the (least-privilege) role defaults."""
    membership = CompanyUser.objects.get(company=tenant.company, user=tenant.staff)
    membership.role = CompanyUser.Role.VIEWER
    for field, value in CompanyUser.capability_defaults_for_role(CompanyUser.Role.VIEWER).items():
        setattr(membership, field, value)
    membership.save()
    return membership


def test_viewer_cannot_post_invoice(tenant_a):
    _demote_staff_to_viewer(tenant_a)

    client = APIClient()
    client.force_authenticate(user=tenant_a.staff)
    resp = client.post(
        "/api/v1/sales/invoices/",
        {"customer": None, "invoice_type": "GST", "items": []},
        format="json",
    )
    assert resp.status_code == 403


def test_invite_viewer_applies_capability_defaults(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {
            "email": "viewer@alpha.test",
            "password": "StrongPass123!",
            "full_name": "Viewer User",
            "role": "VIEWER",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["role"] == "VIEWER"
    assert resp.data["can_create_sales"] is False
    assert resp.data["can_create_purchases"] is False
    assert resp.data["can_create_payments"] is False
    assert resp.data["can_export"] is False
    assert resp.data["can_import"] is False
    assert resp.data["can_cancel_documents"] is False
    # Wave 12B: VIEWER no longer defaults into financial reports visibility.
    assert resp.data["can_view_financial_reports"] is False
    assert resp.data["can_view_ai_insights"] is False
    assert resp.data["can_use_ai_assistant"] is False
    assert resp.data["can_manage_inventory"] is False


def test_invite_viewer_rejects_capability_escalation(tenant_a):
    """BB-000227: VIEWER + write caps rejected at serializer validation."""
    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {
            "email": "viewer-escalated@alpha.test",
            "password": "StrongPass123!",
            "role": "VIEWER",
            "can_create_sales": True,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "can_create_sales" in resp.data["error"]["details"]


def test_invite_accountant_applies_capability_defaults(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {
            "email": "books@alpha.test",
            "password": "StrongPass123!",
            "role": "ACCOUNTANT",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["role"] == "ACCOUNTANT"
    assert resp.data["can_view_financial_reports"] is True
    assert resp.data["can_export"] is True
    assert resp.data["can_create_purchases"] is True
    assert resp.data["can_create_payments"] is True
    assert resp.data["can_create_sales"] is False
    assert resp.data["can_cancel_documents"] is False
    assert resp.data["can_view_ai_insights"] is False
    assert resp.data["can_use_ai_assistant"] is False
    assert resp.data["can_manage_inventory"] is False
    assert resp.data["can_post_journals"] is True


# --- Wave 12B: RBAC surface gates -------------------------------------------------


def test_viewer_cannot_complete_credit_note(tenant_a):
    """VIEWER can never mutate documents, even a credit note it can (maybe) see."""
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "400", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data

    _demote_staff_to_viewer(tenant_a)
    resp = tenant_a.staff_client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code == 403


def test_viewer_cannot_list_journals(tenant_a):
    """VIEWER without can_view_financial_reports cannot list posted journals."""
    from accounting.services import seed_chart_of_accounts

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)

    _demote_staff_to_viewer(tenant_a)
    resp = tenant_a.staff_client.get("/api/v1/accounting/journals/")
    assert resp.status_code == 403


def test_viewer_cannot_get_insights(tenant_a):
    """CanViewAiInsights is gated on can_view_ai_insights only (BB-000297)."""
    _demote_staff_to_viewer(tenant_a)
    resp = tenant_a.staff_client.get("/api/v1/insights/health/")
    assert resp.status_code == 403


def test_staff_without_can_create_sales_cannot_patch_invoice(tenant_a):
    """Sales staff without can_create_sales cannot PATCH a (draft) invoice."""
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )

    resp = tenant_a.staff_client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/", {"notes": "hello"}, format="json"
    )
    assert resp.status_code == 403
