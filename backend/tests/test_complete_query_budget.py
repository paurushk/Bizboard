"""BB-067: queries per sales invoice Complete, and what the ledger adds.

Measured 2026-10-23 (SQLite test DB, second Complete so caches are warm): 102 queries with the
ledger off, 151 with it on. core.services.lookup_cache now fetches the series GSTIN and the
chart check once per Complete (146). The remaining ~44 are per journal (sale and cost of goods)
and deliberate: period rows locked FOR UPDATE against month close, the GST-period gate, the
journal number and the journal itself. Every lookup involved is indexed (Account company+code,
AccountingPeriod company+dates, DocumentSeries, GstReturnPeriod, CompanyGstin).
The budget guards against regressions; lower it when the count drops.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.services.lookup_cache import cached, first_time, lookup_cache, with_lookup_cache
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db

LEDGER_OVERHEAD_BUDGET = 46


def _complete_queries(tenant, *, post_ledger: bool, sku: str, gstin: str) -> int:
    company = tenant.company
    company.gstin, company.state, company.post_ledger = "29ABCDE1234F1ZW", "Karnataka", post_ledger
    company.save()
    product = make_product(company, sku=sku, hsn_code="3004", gst_rate="18")
    add_stock(tenant, product, "50")
    customer = make_customer(company, name=f"Buyer {sku}", state="Karnataka", gstin=gstin)
    payload = {"customer": customer.id, "invoice_type": "GST", "invoice_date": "2026-10-15",
               "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}]}
    count = 0
    for _ in range(2):  # the second Complete is measured: one-time seeding is out of the way
        created = tenant.client.post("/api/v1/sales/invoices/", payload, format="json")
        assert created.status_code == 201, created.data
        with CaptureQueriesContext(connection) as ctx:
            done = tenant.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/")
        assert done.status_code == 200, done.data
        count = len(ctx.captured_queries)
    return count


@pytest.mark.invariant_skip(
    "gl.ar_ties_to_documents",
    reason="one invoice is completed with ledger posting off and one with it on in the same company",
)
def test_ledger_adds_no_more_than_the_budget_to_complete(tenant_a):
    off = _complete_queries(tenant_a, post_ledger=False, sku="QB0", gstin="29AAACR5055K1Z5")
    on = _complete_queries(tenant_a, post_ledger=True, sku="QB1", gstin="29AABCU9603R1ZJ")
    assert on - off <= LEDGER_OVERHEAD_BUDGET, f"ledger adds {on - off} queries to Complete ({off} -> {on})"


def test_lookups_are_memoized_only_inside_the_block():
    calls = []

    def load():
        calls.append(1)
        return "acct"

    assert cached("k", load) == "acct" and cached("k", load) == "acct"
    assert len(calls) == 2  # outside: every call reads
    with lookup_cache():
        assert cached("k", load) == "acct" and cached("k", load) == "acct"
        with lookup_cache():  # nested blocks share the outer memo
            assert cached("k", load) == "acct"
    assert len(calls) == 3
    with lookup_cache():
        cached("k", load)  # a new block starts empty
    assert len(calls) == 4


def test_a_miss_is_not_kept_so_the_caller_can_create_the_row():
    results = iter([None, "created"])
    with lookup_cache():
        assert cached("acct:4100", lambda: next(results)) is None
        assert cached("acct:4100", lambda: next(results)) == "created"
        assert cached("none-ok", lambda: None, keep_none=True) is None
        assert cached("none-ok", lambda: "never read", keep_none=True) is None


def test_first_time_and_decorator_reset_after_an_error():
    @with_lookup_cache
    def op():
        assert first_time("chart") is True and first_time("chart") is False
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        op()
    assert first_time("chart") is True  # outside any block
    with pytest.raises(RuntimeError):
        op()  # a fresh block: the memo did not leak from the failed call
