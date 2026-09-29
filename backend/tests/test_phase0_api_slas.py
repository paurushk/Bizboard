"""Must/Should API timings from PHASE_0_DOD section I.

I1 is the product-list barcode search the POS scan calls. I2, I3, and I5 are
the other section I actions. Keystroke time is not an I1 sample.

Protocol: discard one warm-up, then 20 samples for Must (I1, I2, I3) and 10 for
Should (I5). P95 is the ceil(0.95 * n)th sorted sample, 1-based.
"""

import math
import time
from decimal import Decimal

import pytest

from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    rank = math.ceil(0.95 * len(ordered))
    return ordered[rank - 1]


def test_i1_barcode_lookup_p95_within_100ms(tenant_a):
    """I1 Must: exact barcode search, warm-up discarded, 20 samples, P95 <= 100ms.

    This is the product lookup the POS scan calls (`q` on the product list).
    Keystroke time is not part of the sample.
    """
    target = make_product(tenant_a.company, sku="I1-TARGET", name="Scan target")
    target.barcode = "8901030381014"
    target.save(update_fields=["barcode"])
    for i in range(40):
        make_product(tenant_a.company, sku=f"I1-FILL-{i:03d}", name=f"Filler {i}")

    def _once():
        started = time.perf_counter()
        resp = tenant_a.client.get("/api/v1/products/", {"q": "8901030381014"})
        elapsed = time.perf_counter() - started
        assert resp.status_code == 200, resp.data
        rows = resp.data.get("results", resp.data)
        assert any(row.get("barcode") == "8901030381014" or row.get("sku") == "I1-TARGET" for row in rows)
        return elapsed

    _once()
    samples = [_once() for _ in range(20)]
    observed = _p95(samples)
    assert observed <= 0.100, f"I1 P95 {observed:.3f}s over 20 samples (SLA <= 0.100s). samples={samples}"


def test_i2_invoice_complete_roundtrip_p95_within_800ms(tenant_a):
    """I2 Must: create + complete, warm-up discarded, 20 samples, P95 <= 800ms."""
    product = make_product(tenant_a.company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "40", unit_cost="60")
    customer = make_customer(tenant_a.company, state="Karnataka")

    def _once():
        started = time.perf_counter()
        created = create_draft_invoice(
            tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        )
        completed = tenant_a.client.post(f"/api/v1/sales/invoices/{created['id']}/complete/")
        elapsed = time.perf_counter() - started
        assert completed.status_code == 200, completed.data
        assert Decimal(str(completed.data["grand_total"])) == Decimal("118.00")
        return elapsed

    _once()
    samples = [_once() for _ in range(20)]
    observed = _p95(samples)
    assert observed <= 0.800, f"I2 P95 {observed:.3f}s over 20 samples (SLA <= 0.800s). samples={samples}"


def test_i3_fifty_row_product_list_p95_within_400ms(tenant_a):
    """I3 Must: one page of 50 products, warm-up discarded, 20 samples, P95 <= 400ms."""
    for i in range(50):
        make_product(tenant_a.company, sku=f"I3-{i:03d}", name=f"Row {i}")

    def _once():
        started = time.perf_counter()
        resp = tenant_a.client.get("/api/v1/products/")
        elapsed = time.perf_counter() - started
        assert resp.status_code == 200, resp.data
        rows = resp.data.get("results", resp.data)
        assert len(rows) == 50
        return elapsed

    _once()
    samples = [_once() for _ in range(20)]
    observed = _p95(samples)
    assert observed <= 0.400, f"I3 P95 {observed:.3f}s over 20 samples (SLA <= 0.400s). samples={samples}"


def test_product_list_repeat_stays_stable(tenant_a):
    """Thirty reads of the same catalog return the same count. Query count does not grow."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    for i in range(15):
        make_product(tenant_a.company, sku=f"REL-{i:03d}")
    tenant_a.client.get("/api/v1/products/")
    counts = []
    query_counts = []
    for _ in range(30):
        with CaptureQueriesContext(connection) as ctx:
            resp = tenant_a.client.get("/api/v1/products/")
        assert resp.status_code == 200, resp.data
        rows = resp.data.get("results", resp.data)
        counts.append(len(rows))
        query_counts.append(len(ctx.captured_queries))
    assert len(set(counts)) == 1
    assert max(query_counts) <= min(query_counts) + 2


def test_i5_invoice_pdf_generation_p95_within_2_5s(tenant_a):
    """I5 Should: generate_invoice_pdf, warm-up discarded, 10 samples, P95 <= 2.5s."""
    from sales.tasks import generate_invoice_pdf

    product = make_product(tenant_a.company, gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "5", unit_cost="40")
    customer = make_customer(tenant_a.company)
    created = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{created['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=created["id"])

    def _once():
        started = time.perf_counter()
        generate_invoice_pdf.run(invoice.id, company_id=tenant_a.company.id)
        return time.perf_counter() - started

    _once()
    samples = [_once() for _ in range(10)]
    observed = _p95(samples)
    assert observed <= 2.5, f"I5 P95 {observed:.3f}s over 10 samples (SLA <= 2.5s). samples={samples}"
