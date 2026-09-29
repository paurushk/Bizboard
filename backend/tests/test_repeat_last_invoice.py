"""Repeat-Last-Invoice: copy a customer's most recently COMPLETED invoice's
line items into a new, fully editable DRAFT invoice for the same customer.

Covers ``SalesService.repeat_last_invoice`` and the
``POST /api/v1/sales/invoices/repeat-last/`` action.
"""

from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from sales.models import SalesInvoice
from sales.services import SalesService
from tests.conftest import add_stock, make_customer, make_product


@pytest.mark.django_db
def test_customer_with_no_prior_invoice_gets_a_clear_error(tenant_a):
    customer = make_customer(tenant_a.company)
    with pytest.raises(BusinessRuleError, match="no completed invoice"):
        SalesService.repeat_last_invoice(tenant_a.company, customer, tenant_a.owner)


@pytest.mark.django_db
def test_api_repeat_last_with_no_prior_invoice_is_a_clean_400(tenant_a):
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/repeat-last/", {"customer": customer.id}, format="json",
    )
    assert resp.status_code == 400, resp.data


@pytest.mark.django_db
def test_customer_with_prior_invoice_gets_populated_draft(tenant_a):
    product = make_product(tenant_a.company, sku="REPEAT-1", selling_price="250")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    draft = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [
                {"product": product.id, "quantity": "3", "unit_price": "180", "discount_percent": "5"},
            ],
        },
        format="json",
    )
    assert draft.status_code == 201, draft.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data

    repeated = SalesService.repeat_last_invoice(tenant_a.company, customer, tenant_a.owner)
    assert repeated.status == SalesInvoice.Status.DRAFT
    assert repeated.customer_id == customer.id
    assert repeated.pk != draft.data["id"]
    items = list(repeated.items.all())
    assert len(items) == 1
    item = items[0]
    assert item.product_id == product.id
    assert item.quantity == Decimal("3")
    assert item.unit_price == Decimal("180")
    assert item.discount_percent == Decimal("5")


@pytest.mark.django_db
def test_repeated_draft_is_independent_of_the_original(tenant_a):
    product = make_product(tenant_a.company, sku="REPEAT-2", selling_price="100")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    draft = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
        },
        format="json",
    )
    assert draft.status_code == 201, draft.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data
    original = SalesInvoice.objects.get(pk=draft.data["id"])
    original_item = original.items.get()

    repeated = SalesService.repeat_last_invoice(tenant_a.company, customer, tenant_a.owner)

    # Edit the copy: change quantity via the normal edit path.
    SalesService.set_items(
        repeated,
        [{"product": product, "quantity": Decimal("9"), "unit_price": Decimal("100")}],
        tenant_a.owner,
    )
    repeated.refresh_from_db()
    original_item.refresh_from_db()

    assert repeated.items.get().quantity == Decimal("9")
    # The original, completed invoice's line is untouched.
    assert original_item.quantity == Decimal("2")
    assert SalesInvoice.objects.get(pk=original.pk).status == SalesInvoice.Status.COMPLETED


@pytest.mark.django_db
def test_repeated_draft_completes_through_all_normal_gates(tenant_a):
    """The new draft is not a bypass -- it still goes through GST Guard and
    every other completion gate when it is later completed."""
    product = make_product(tenant_a.company, sku="REPEAT-3", hsn_code="", gst_rate="18")
    add_stock(tenant_a, product, "10")
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["state"])
    customer = make_customer(
        tenant_a.company, gstin="29AAAAA0000A1ZY", state="Karnataka",
    )
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_GST_GUARD"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])

    draft = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert draft.status_code == 201, draft.data
    # This first completion is itself blocked by GST Guard (missing HSN, B2B) --
    # override it so we have a COMPLETED source invoice to repeat.
    ok = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft.data['id']}/complete/",
        {"gst_guard_override_reason": "test fixture setup"},
        format="json",
    )
    assert ok.status_code == 200, ok.data

    repeated = SalesService.repeat_last_invoice(tenant_a.company, customer, tenant_a.owner)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{repeated.pk}/complete/")
    # Same missing-HSN-on-B2B-line issue as the source -- still blocked, proving
    # the copy is not exempt from GST Guard.
    assert resp.status_code == 400, resp.data
    err = resp.data.get("error") or resp.data
    assert err.get("code") == "gst_guard_blocked"
