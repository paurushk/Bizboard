"""BB-000018: staff without can_create_sales cannot create sales invoices."""

from accounts.models import CompanyUser


def test_staff_cannot_create_sales_when_flag_false(tenant_a):
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_create_sales = False
    membership.save(update_fields=["can_create_sales"])

    resp = tenant_a.staff_client.post(
        "/api/v1/sales/invoices/",
        {"customer": None, "invoice_type": "GST", "items": []},
        format="json",
    )
    assert resp.status_code == 403


def test_pos_checkout_requires_can_create_sales(tenant_a):
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_create_sales = False
    membership.can_create_payments = True
    membership.save(update_fields=["can_create_sales", "can_create_payments"])

    resp = tenant_a.staff_client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {"invoice": {"customer": None, "invoice_type": "RETAIL", "items": []}},
        format="json",
    )
    assert resp.status_code == 403


def test_pos_checkout_requires_can_create_payments(tenant_a):
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_create_sales = True
    membership.can_create_payments = False
    membership.save(update_fields=["can_create_sales", "can_create_payments"])

    resp = tenant_a.staff_client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {"invoice": {"customer": None, "invoice_type": "RETAIL", "items": []}},
        format="json",
    )
    assert resp.status_code == 403
