"""COMP-009: billing stays a shim and every tenant gets the India pack."""

import inspect
from decimal import Decimal

import pytest

import core.services.billing as billing
import core.services.tax_engine.india as india
import purchases.notes_services as purchase_notes
import purchases.services as purchase_services
import sales.challan_return as challan_return
import sales.notes_services as sales_notes
import sales.return_service as sales_returns
import sales.services as sales_services
from core.services.billing import compute_document_totals, get_tax_engine, q2
from core.services.tax_engine.india import IndiaTaxEngine


def test_q2_still_imports_from_billing():
    assert q2(Decimal("1.005")) == Decimal("1.01")
    assert compute_document_totals.__module__ == "core.services.tax_engine.india"


def test_billing_shim_has_no_local_reimplementation_of_any_reexported_name():
    """F1-005 (top test-gap from the COMP-009 review): every name billing.py
    re-exports must be the EXACT SAME object as the one in tax_engine.india —
    not a local copy/reimplementation that could silently drift from the
    real implementation. Catches the failure mode this refactor exists to
    guard against: a future edit accidentally patching billing.py instead of
    india.py (or vice versa), producing two copies of the same GST math that
    quietly diverge.
    """
    for name in billing.__all__:
        if name == "get_tax_engine":
            continue  # lives in tax_engine.registry, not tax_engine.india
        assert hasattr(india, name), f"{name} is in billing.__all__ but missing from tax_engine.india"
        assert getattr(billing, name) is getattr(india, name), (
            f"core.services.billing.{name} is not the same object as "
            f"core.services.tax_engine.india.{name} — one of them has a local "
            f"reimplementation instead of a re-export."
        )


@pytest.mark.django_db
def test_build_totals_preview_item_shape_is_pinned(tenant_a):
    """Would have caught the extra `gst_rate` key that slipped into the
    "moved unchanged" refactor (build_totals_preview's per-item dict gained
    a key the original billing.py never emitted): pins the exact key set of
    one preview line item, via the real preview-totals endpoint that
    actually returns this dict as an API response body, so a future edit
    can't silently grow/shrink the response shape unnoticed.
    """
    from tests.conftest import make_customer, make_product

    product = make_product(tenant_a.company, sku="TE-1", hsn_code="3004", gst_rate="18")
    customer = make_customer(tenant_a.company)
    payload = {
        "customer": customer.id,
        "invoice_type": "NON_GST",
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }
    preview = tenant_a.client.post("/api/v1/sales/invoices/preview-totals/", payload, format="json")
    assert preview.status_code == 200, preview.data
    assert set(preview.data["items"][0].keys()) == {
        "taxable_amount", "cgst", "sgst", "igst", "cess", "line_total",
    }


@pytest.mark.django_db
def test_get_tax_engine_returns_india_pack(tenant_a, tenant_b):
    for company in (tenant_a.company, tenant_b.company, None):
        engine = get_tax_engine(company)
        assert isinstance(engine, IndiaTaxEngine)
        assert engine.round_amount(Decimal("2.005")) == Decimal("2.01")


def test_sales_and_purchase_totals_use_the_engine():
    modules = (
        sales_services,
        sales_notes,
        sales_returns,
        challan_return,
        purchase_services,
        purchase_notes,
    )
    for module in modules:
        source = inspect.getsource(module)
        assert "get_tax_engine(" in source
        for line in source.splitlines():
            if "import" in line and "compute_document_totals" in line:
                raise AssertionError(f"{module.__name__} still imports compute_document_totals")


@pytest.mark.django_db
def test_draft_invoice_totals_go_through_the_engine(tenant_a, monkeypatch):
    from tests.conftest import create_draft_invoice, make_customer, make_product

    seen = {}
    real = IndiaTaxEngine.compute_document_totals

    def wrapped(self, document, items, **kwargs):
        seen["document"] = document
        return real(self, document, items, **kwargs)

    monkeypatch.setattr(IndiaTaxEngine, "compute_document_totals", wrapped)
    product = make_product(tenant_a.company, sku="ENG-1")
    customer = make_customer(tenant_a.company)
    create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        invoice_type="NON_GST",
    )
    assert seen["document"].customer_id == customer.id
