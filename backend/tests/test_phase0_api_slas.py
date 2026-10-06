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


# The SLAs below are defined for an application server next to its database (same host / same VPC: a
# round trip of well under a millisecond). Measured on 2026-10-02, a developer laptop reaching Postgres
# through Docker Desktop has a 3.5 ms median and a 16 ms p99 round trip; a create+complete issues about
# 90 queries, so ~350 ms of its wall time is network latency and the tail is network jitter, none of it
# application code. Wall-clock assertions are therefore enforced only where the database is close, and
# the part that IS the application's responsibility, how many queries it makes, is asserted everywhere
# (see test_i2_create_and_complete_query_budget).
CLOSE_DB_RTT_MS = 1.5


def _db_rtt_ms(samples: int = 100) -> float:
    from django.db import connection

    timings = []
    with connection.cursor() as cur:
        cur.execute("SELECT 1")  # connect + warm up
        for _ in range(samples):
            t = time.perf_counter()
            cur.execute("SELECT 1")
            cur.fetchone()
            timings.append((time.perf_counter() - t) * 1000)
    timings.sort()
    return timings[len(timings) // 2]


def _require_close_db():
    rtt = _db_rtt_ms()
    if rtt > CLOSE_DB_RTT_MS:
        pytest.skip(
            f"database round trip is {rtt:.2f} ms (median); the wall-clock SLA assumes <= {CLOSE_DB_RTT_MS} ms. "
            "Enforced on CI (database on the same host). The query budget test still runs here."
        )


def test_i1_barcode_lookup_p95_within_100ms(tenant_a):
    """I1 Must: exact barcode search, warm-up discarded, 20 samples, P95 <= 100ms.

    This is the product lookup the POS scan calls (`q` on the product list).
    Keystroke time is not part of the sample.
    """
    _require_close_db()
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
    """I2 Must: create + complete, warm-up discarded, 20 samples, P95 <= 800ms.

    The SLO is "ex-PDF, ex-GSP" (load/README.md, X-01): in production the PDF is queued to Celery after
    Complete returns. The test settings run Celery eagerly, which would render the PDF INSIDE the timed
    request; profiled on 2026-10-02 that was ~330 ms of a ~710 ms round trip (complete 585 ms with the
    eager PDF, 259 ms without). So the measurement runs with PDF enqueueing suppressed, which is exactly
    what the SLO covers. test_i2_pdf_is_queued_not_rendered_inline_in_production_mode proves the other half."""
    _require_close_db()
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

    from core.seed_guard import seed_load_scope

    with seed_load_scope():  # no PDF / notification side effects: the SLO is ex-PDF
        _once()
        samples = [_once() for _ in range(20)]
    observed = _p95(samples)
    assert observed <= 0.800, f"I2 P95 {observed:.3f}s over 20 samples (SLA <= 0.800s). samples={samples}"


def test_i3_fifty_row_product_list_p95_within_400ms(tenant_a):
    """I3 Must: one page of 50 products, warm-up discarded, 20 samples, P95 <= 400ms."""
    _require_close_db()
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


def test_i2_pdf_is_queued_not_rendered_inline_in_production_mode(tenant_a, settings, django_capture_on_commit_callbacks):
    """Companion to the I2 SLA: outside eager mode Complete only REGISTERS the PDF job to run after the
    transaction commits, so the request time the SLO measures really does exclude PDF rendering."""
    from unittest import mock

    from sales.models import SalesInvoice

    settings.CELERY_TASK_ALWAYS_EAGER = False
    product = make_product(tenant_a.company, gst_rate="18", selling_price="100", sku="I2-PDF")
    add_stock(tenant_a, product, "5", unit_cost="60")
    customer = make_customer(tenant_a.company, state="Karnataka")
    created = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    with mock.patch("sales.handlers.safe_delay") as queued:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            resp = tenant_a.client.post(f"/api/v1/sales/invoices/{created['id']}/complete/")
    assert resp.status_code == 200, resp.data
    queued.assert_not_called()          # nothing was enqueued or rendered inside the request itself
    assert callbacks, "the PDF job must be registered to run after commit"
    assert SalesInvoice.objects.get(pk=created["id"]).pdf_status == SalesInvoice.PdfStatus.QUEUED


# --- environment-independent half of the I2 SLA --------------------------------------------------

# Measured 2026-10-02 after the invoice-response memo: create 18 queries, complete ~70 (no PDF). The budget
# leaves ~15 % headroom for legitimate growth and fails an N+1 (a per-line query would add one per line).
# 105 -> 108 for the audit row, party snapshot and job-card hold release now written inside
# complete (BUG-SEC-016, party snapshots, BUG-WRK-002). Not a licence to add more.
I2_QUERY_BUDGET = 108


def _queries_for_create_and_complete(tenant_a, lines: int):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from core.seed_guard import seed_load_scope

    customer = make_customer(tenant_a.company, state="Karnataka")
    products = []
    for i in range(lines):
        p = make_product(tenant_a.company, gst_rate="18", selling_price="100", sku=f"QB-{lines}-{i}")
        add_stock(tenant_a, p, "40", unit_cost="60")
        products.append(p)
    body = [{"product": p.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"} for p in products]
    create_draft_invoice(tenant_a, customer, body)  # warm caches (flags, series)
    with seed_load_scope(), CaptureQueriesContext(connection) as ctx:
        created = create_draft_invoice(tenant_a, customer, body)
        done = tenant_a.client.post(f"/api/v1/sales/invoices/{created['id']}/complete/")
    assert done.status_code == 200, done.data
    return len(ctx)


def test_i2_create_and_complete_query_budget(tenant_a):
    n = _queries_for_create_and_complete(tenant_a, lines=1)
    print(f"I2 create+complete queries (1 line): {n}")
    assert n <= I2_QUERY_BUDGET, f"create+complete now issues {n} queries (budget {I2_QUERY_BUDGET}); look for a new N+1"


# Known performance debt, recorded as a ratchet rather than hidden. Measured 2026-10-02: one line costs 94
# queries, five lines cost 160, i.e. ~16.5 extra queries for every line added (stock movement, running
# cost, tax and batch lookups happen per line). Over a 3.5 ms Docker round trip that is ~58 ms per line;
# on a close database about 5 ms. The goal is to LOWER this number; the test stops it getting worse.
I2_PER_LINE_QUERY_CEILING = 18


def test_i2_query_count_growth_per_line_is_ratcheted(tenant_a):
    """The N+1 ratchet: queries added per extra line. Fails if it rises above the measured ceiling.
    Lower I2_PER_LINE_QUERY_CEILING when the per-line work is batched (it should be, see QOS-0003)."""
    one = _queries_for_create_and_complete(tenant_a, lines=1)
    five = _queries_for_create_and_complete(tenant_a, lines=5)
    per_extra_line = (five - one) / 4
    print(f"I2 queries: 1 line={one}, 5 lines={five}, per extra line={per_extra_line:.1f}")
    assert per_extra_line <= I2_PER_LINE_QUERY_CEILING, (
        f"{per_extra_line:.1f} extra queries per added line (ceiling {I2_PER_LINE_QUERY_CEILING}; 1 line: {one}, 5 lines: {five})"
    )


def test_wall_clock_sla_is_skipped_only_when_the_database_is_far(monkeypatch):
    import tests.test_phase0_api_slas as mod

    monkeypatch.setattr(mod, "_db_rtt_ms", lambda samples=100: 3.5)
    with pytest.raises(pytest.skip.Exception) as ei:
        mod._require_close_db()
    assert "3.50 ms" in str(ei.value) and "query budget" in str(ei.value)
    monkeypatch.setattr(mod, "_db_rtt_ms", lambda samples=100: 0.2)
    mod._require_close_db()  # a close database must NOT skip: the SLA is enforced


def test_the_close_database_threshold_matches_what_the_sla_assumes():
    assert CLOSE_DB_RTT_MS <= 2.0
