"""Price-jump note on a purchase line: informational, read-only, no blocking.

Reuses the same PurchaseItem query as supplier price history (COMP-007) — see
purchases.reliability.last_completed_purchase_rate.
"""

from datetime import date
from decimal import Decimal

import pytest

from purchases.models import PurchaseInvoice, PurchaseItem
from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _enable(company):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_SUPPLIER_PRICE_HISTORY"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _completed_invoice(company, supplier, product, price, *, number, invoice_date):
    invoice = PurchaseInvoice.objects.create(
        company=company, supplier=supplier, number=number,
        status=PurchaseInvoice.Status.COMPLETED, invoice_date=invoice_date,
    )
    PurchaseItem.objects.create(
        company=company, invoice=invoice, product=product,
        quantity=Decimal("2"), unit_price=Decimal(price), description="item",
    )
    return invoice


def test_higher_rate_shows_note_with_last_rate_and_date(tenant_a):
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PJ-1")
    _completed_invoice(tenant_a.company, supplier, product, "10", number="PJ-OLD", invoice_date=date(2026, 1, 1))

    data = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "15"}],
    )
    note = data["items"][0]["price_jump_note"]
    assert note is not None
    assert "10" in note
    assert "2026-01-01" in note


def test_equal_or_lower_rate_shows_no_note(tenant_a):
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PJ-2")
    _completed_invoice(tenant_a.company, supplier, product, "10", number="PJ-OLD2", invoice_date=date(2026, 1, 1))

    equal = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "10"}],
    )
    assert equal["items"][0]["price_jump_note"] is None

    lower = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "8"}],
    )
    assert lower["items"][0]["price_jump_note"] is None


def test_no_history_shows_no_note_and_does_not_error(tenant_a):
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company, name="Cold Start Supplier")
    product = make_product(tenant_a.company, sku="PJ-3")

    data = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "50"}],
    )
    assert data["items"][0]["price_jump_note"] is None


def test_only_completed_history_counts(tenant_a):
    """A cancelled/draft prior purchase must not be treated as the 'last' rate."""
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company, name="Draft History Supplier")
    product = make_product(tenant_a.company, sku="PJ-4")
    draft = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, number="PJ-DRAFT",
        status=PurchaseInvoice.Status.DRAFT, invoice_date=date(2026, 1, 1),
    )
    PurchaseItem.objects.create(
        company=tenant_a.company, invoice=draft, product=product,
        quantity=Decimal("2"), unit_price=Decimal("500"), description="draft item",
    )
    data = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "12"}],
    )
    assert data["items"][0]["price_jump_note"] is None


def test_price_jump_note_does_not_requery_per_line(tenant_a, django_assert_max_num_queries):
    """Regression for a fixed N+1: fetching one purchase invoice with several
    lines (each needing its own supplier-price-history lookup) must batch
    that lookup once for the invoice, not once per line.
    """
    _enable(tenant_a.company)
    supplier = make_supplier(tenant_a.company, name="Many Lines Supplier")
    products = [make_product(tenant_a.company, sku=f"PJ-MANY-{i}") for i in range(8)]
    for product in products:
        _completed_invoice(
            tenant_a.company, supplier, product, "10",
            number=f"PJ-HIST-{product.sku}", invoice_date=date(2026, 1, 1),
        )
    data = create_draft_purchase(
        tenant_a, supplier,
        [{"product": p.id, "quantity": "1", "unit_price": "20"} for p in products],
    )
    assert all(item["price_jump_note"] is not None for item in data["items"])

    # The write above (8 line inserts) is out of scope for this bound — only
    # the read path matters here. 8 distinct products, one supplier: without
    # batching this would be at least 8 extra queries just for the notes.
    with django_assert_max_num_queries(15):
        resp = tenant_a.client.get(f"/api/v1/purchases/invoices/{data['id']}/")
    assert resp.status_code == 200, resp.data
    assert all(item["price_jump_note"] is not None for item in resp.data["items"])


def test_note_hidden_when_feature_flag_off(tenant_a):
    supplier = make_supplier(tenant_a.company, name="Flag Off Supplier")
    product = make_product(tenant_a.company, sku="PJ-5")
    _completed_invoice(tenant_a.company, supplier, product, "10", number="PJ-OLD5", invoice_date=date(2026, 1, 1))
    data = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "20"}],
    )
    assert data["items"][0]["price_jump_note"] is None
