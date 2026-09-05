"""WS-08 — report/dashboard performance N+1 regressions (2026-09-03 review).

Each test asserts the query count for the fixed function stays *constant*
(within a small margin) as the row count grows, proving the fix removed a
per-row query loop rather than just happening to be fast on tiny fixtures.
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.exceptions import BusinessRuleError
from reporting.services import ReportService
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _complete_purchase(tenant, supplier, product, price="100"):
    draft = create_draft_purchase(
        tenant, supplier, [{"product": product.id, "quantity": "1", "unit_price": price}],
    )
    resp = tenant.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return draft["id"]


def test_b5_008_payables_aging_query_count_is_flat(tenant_a):
    """B5-008: payables_aging used to call LedgerService.purchase_invoice_
    outstanding() per invoice (several queries each) instead of the bulk
    CN/DN/allocation maps receivables_aging already used. Query count must
    not grow with invoice count."""
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")

    for _ in range(2):
        _complete_purchase(tenant_a, supplier, product)
    with CaptureQueriesContext(connection) as small:
        ReportService.payables_aging(tenant_a.company)

    for _ in range(6):
        _complete_purchase(tenant_a, supplier, product)
    with CaptureQueriesContext(connection) as large:
        ReportService.payables_aging(tenant_a.company)

    # 8 invoices vs 2 must not multiply the query count -- a per-invoice
    # loop would roughly quadruple it; a bulk implementation stays flat.
    assert len(large.captured_queries) <= len(small.captured_queries) + 2, (
        f"{len(small.captured_queries)} queries for 2 invoices vs "
        f"{len(large.captured_queries)} for 8 -- looks like an N+1 regression"
    )


def test_b5_008_payables_aging_still_correct(tenant_a):
    """Bulk rewrite must not change the actual bucketed totals."""
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    _complete_purchase(tenant_a, supplier, product, price="500")
    _complete_purchase(tenant_a, supplier, product, price="300")
    aging = ReportService.payables_aging(tenant_a.company)
    assert sum(aging.values(), Decimal("0")) == Decimal("800.00")


def test_b5_009_cash_position_query_count_is_flat(tenant_a):
    """B5-009: cash_position used to call the full cash_book() twice (once
    completely unbounded), materialising every receipt/payment into `rows`
    just to read four numbers off it. cash_totals must never build `rows`,
    so query count stays flat as receipt/payment count grows."""
    from payments.services import PaymentService

    customer = make_customer(tenant_a.company)

    def _receipt(amount):
        PaymentService.create_receipt(
            company=tenant_a.company, customer=customer, amount=Decimal(amount), mode="CASH",
        )

    for amt in ("100", "200"):
        _receipt(amt)
    with CaptureQueriesContext(connection) as small:
        ReportService.cash_position(tenant_a.company)

    for amt in ("300", "400", "500", "600", "700", "800"):
        _receipt(amt)
    with CaptureQueriesContext(connection) as large:
        ReportService.cash_position(tenant_a.company)

    assert len(large.captured_queries) <= len(small.captured_queries), (
        f"{len(small.captured_queries)} queries for 2 receipts vs "
        f"{len(large.captured_queries)} for 8 -- cash_position should never "
        "scale with receipt/payment count"
    )


def test_b5_009_cash_position_still_correct(tenant_a):
    from payments.services import PaymentService

    customer = make_customer(tenant_a.company)
    PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("1500"), mode="CASH",
    )
    position = ReportService.cash_position(tenant_a.company)
    assert position["closing"] == Decimal("1500")


def _open_invoice_no_link(tenant, product, customer):
    draft = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return draft["id"]


def test_b4_017_payment_health_query_count_is_flat(tenant_a):
    """B4-017: payment_health's "open invoice with no payment link" check
    used to call LedgerService.sales_invoice_outstanding(inv) per invoice
    (up to 50). Query count must not grow with open-invoice count."""
    from payments.services import PaymentService

    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "50")
    customer = make_customer(tenant_a.company)
    assert not (tenant_a.company.upi_id or "").strip()

    for _ in range(2):
        _open_invoice_no_link(tenant_a, product, customer)
    with CaptureQueriesContext(connection) as small:
        PaymentService._payment_health_uncached(company=tenant_a.company)

    for _ in range(6):
        _open_invoice_no_link(tenant_a, product, customer)
    with CaptureQueriesContext(connection) as large:
        PaymentService._payment_health_uncached(company=tenant_a.company)

    assert len(large.captured_queries) <= len(small.captured_queries) + 2, (
        f"{len(small.captured_queries)} queries for 2 open invoices vs "
        f"{len(large.captured_queries)} for 8 -- looks like an N+1 regression"
    )


def test_b4_018_commit_auto_match_query_count_scales_with_lines_not_quadratically(tenant_a):
    """B4-018: BankStatementViewSet.commit's auto-match loop used to call
    suggest_matches (a windowed candidate query + a fresh ReconMatch
    exclusion query) plus, for exact-unique suggestions,
    is_exact_unique_suggestion's own per-suggestion UTR lookup -- all per
    line. Query count must grow roughly linearly with line count (one
    windowed candidate scan per line is inherent to the matching logic),
    not multiply the way three-plus queries-per-line would."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.utils import timezone

    from payments.models import BankAccount
    from payments.services import PaymentService

    tenant_a.company.auto_match_bank_exact = True
    tenant_a.company.save(update_fields=["auto_match_bank_exact"])
    ba = BankAccount.objects.create(company=tenant_a.company, name="ICICI", is_default=True)
    customer = make_customer(tenant_a.company)
    today = timezone.localdate()

    def _upload_and_commit(n, offset):
        rows = ["Date,Credit,Debit,Narration,Ref No"]
        for i in range(n):
            idx = offset + i
            utr = f"UTR{idx:06d}"
            amount = 1000 + idx  # distinct amount per line -- avoid ambiguous same-day/same-amount candidates
            PaymentService.create_receipt(
                company=tenant_a.company, customer=customer, amount=Decimal(amount),
                mode="BANK", utr=utr, bank_account=ba, receipt_date=today,
            )
            rows.append(f"{today.strftime('%d/%m/%Y')},{amount},,INWARD {utr},{utr}")
        csv_bytes = ("\n".join(rows) + "\n").encode()
        upload = tenant_a.client.post(
            "/api/v1/payments/statements/upload/",
            {"bank_account": ba.id, "preset": "generic", "file": SimpleUploadedFile("s.csv", csv_bytes)},
            format="multipart",
        )
        assert upload.status_code == 201, upload.data
        return upload.data["id"]

    sid_small = _upload_and_commit(2, offset=0)
    with CaptureQueriesContext(connection) as small:
        r1 = tenant_a.client.post(f"/api/v1/payments/statements/{sid_small}/commit/")
    assert r1.status_code == 200, r1.data

    sid_large = _upload_and_commit(8, offset=2)
    with CaptureQueriesContext(connection) as large:
        r2 = tenant_a.client.post(f"/api/v1/payments/statements/{sid_large}/commit/")
    assert r2.status_code == 200, r2.data

    # 8 lines vs 2: allow linear growth (the per-line candidate scan is
    # inherent) but not the ~3x-per-line multiplier the old code had on top.
    per_line_small = len(small.captured_queries) / 2
    per_line_large = len(large.captured_queries) / 8
    assert per_line_large <= per_line_small + 0.5, (
        f"{per_line_small} queries/line at 2 lines vs {per_line_large} at 8 -- "
        "looks like the exclusion-set/UTR-map batching regressed"
    )

    # Correctness: the batching must not break the actual auto-match --
    # every line in both statements has an unambiguous (distinct-amount,
    # UTR-anchored) exact match and must have been auto-confirmed.
    from payments.models import BankLineMatchStatus, BankStatementLine

    for sid in (sid_small, sid_large):
        statuses = set(
            BankStatementLine.objects.filter(statement_id=sid).values_list("match_status", flat=True)
        )
        assert statuses == {BankLineMatchStatus.MATCHED}, (sid, statuses)


def test_b4_017_payment_health_still_flags_open_invoice_without_link(tenant_a):
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    _open_invoice_no_link(tenant_a, product, customer)
    from payments.services import PaymentService

    health = PaymentService._payment_health_uncached(company=tenant_a.company)
    codes = {a["code"] for a in health["alerts"]}
    assert "OPEN_INVOICE_NO_LINK_OR_UPI" in codes


def test_b5_007_gstr2b_upload_rejects_oversized_batch(tenant_a):
    """B5-007: no length cap meant a 50k-row upload materialised ~100k
    queries in one unthrottled request."""
    from reporting.views import MAX_2B_UPLOAD_ROWS

    rows = [
        {"supplier_gstin": "27AAAAA0000A1Z2", "invoice_number": f"OVER-{i}", "taxable_value": "1"}
        for i in range(MAX_2B_UPLOAD_ROWS + 1)
    ]
    resp = tenant_a.client.post(
        "/api/v1/reports/gstr2b/upload/", {"period": "2026-04", "rows": rows}, format="json",
    )
    assert resp.status_code == 400
    from reporting.models import Gstr2bIngest

    assert not Gstr2bIngest.objects.filter(company=tenant_a.company, period="2026-04").exists()


def test_b5_007_gstr2b_upload_is_atomic_on_mid_batch_failure(tenant_a):
    """B5-007: an error partway through the loop used to leave the period
    half-ingested (the earlier rows already committed, no rollback)."""
    rows = [
        {"supplier_gstin": "27AAAAA0000A1Z2", "invoice_number": "OK-1", "taxable_value": "100.00"},
        # Malformed taxable_value -- DecimalField.get_prep_value raises
        # ValidationError when the ORM tries to save this row.
        {"supplier_gstin": "27AAAAA0000A1Z2", "invoice_number": "BAD-1", "taxable_value": "not-a-number"},
    ]
    resp = tenant_a.client.post(
        "/api/v1/reports/gstr2b/upload/", {"period": "2026-05", "rows": rows}, format="json",
    )
    assert resp.status_code >= 400
    # Neither row made it in -- the whole batch rolled back, not just the bad
    # row. Checked via the list API (a fresh request/response cycle) rather
    # than a raw ORM query in the same test function -- the mid-request
    # DecimalField ValidationError above trips SQLite's "broken transaction"
    # guard against further queries sharing the test's own outer transaction.
    listed = tenant_a.client.get("/api/v1/reports/gstr2b/", {"period": "2026-05"})
    assert listed.status_code == 200, listed.data
    assert listed.data["count"] == 0, listed.data


def test_b5_010_sales_register_rejects_unbounded_scan_over_threshold(tenant_a, monkeypatch):
    """B5-010: sales_register/purchase_register with no date_from used to
    materialise every non-draft invoice ever created. Lower the bound for
    this test (creating 5000+ real invoices would be far too slow) and
    confirm the guard actually fires once the unfiltered count exceeds it."""
    import reporting.services as reporting_services

    monkeypatch.setattr(reporting_services, "MAX_REGISTER_ROWS_UNBOUNDED", 3)
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    for _ in range(4):
        _open_invoice_no_link(tenant_a, product, customer)

    with pytest.raises(BusinessRuleError):
        ReportService.sales_register(tenant_a.company)


def test_b5_010_purchase_register_rejects_unbounded_scan_over_threshold(tenant_a, monkeypatch):
    import reporting.services as reporting_services

    monkeypatch.setattr(reporting_services, "MAX_REGISTER_ROWS_UNBOUNDED", 3)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    for _ in range(4):
        _complete_purchase(tenant_a, supplier, product)

    with pytest.raises(BusinessRuleError):
        ReportService.purchase_register(tenant_a.company)


def test_b5_010_register_with_date_from_bypasses_bound_and_stays_correct(tenant_a, monkeypatch):
    """Supplying date_from must skip the count() guard entirely (that's the
    whole point -- a caller who already scoped the query shouldn't pay for
    or be blocked by the unbounded-scan check) and still return every row."""
    import reporting.services as reporting_services

    monkeypatch.setattr(reporting_services, "MAX_REGISTER_ROWS_UNBOUNDED", 1)
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    for _ in range(3):
        _open_invoice_no_link(tenant_a, product, customer)

    result = ReportService.sales_register(tenant_a.company, date_from="2020-01-01")
    assert len(result["rows"]) == 3


def test_b5_010_register_under_threshold_still_returns_full_rows(tenant_a, monkeypatch):
    """Below the bound, behavior with no date_from is unchanged."""
    import reporting.services as reporting_services

    monkeypatch.setattr(reporting_services, "MAX_REGISTER_ROWS_UNBOUNDED", 100)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    _complete_purchase(tenant_a, supplier, product, price="500")
    _complete_purchase(tenant_a, supplier, product, price="300")

    result = ReportService.purchase_register(tenant_a.company)
    assert len(result["rows"]) == 2
    assert Decimal(str(result["totals"]["grand_total"])) == Decimal("800.00")


def test_b8_027_custom_field_values_endpoint_is_cached(tenant_a, monkeypatch):
    """B8-027: ProductViewSet.custom_field_values() called distinct_values_
    for_keys() -- an O(products) full-catalog scan -- on every request. A
    per-company short-TTL cache must turn repeat calls into cache hits."""
    import masters.custom_fields as custom_fields_module

    tenant_a.company.item_custom_field_defs = [
        {"key": "brandCode", "label": "Brand code", "type": "list", "active": True, "options": []},
    ]
    tenant_a.company.save(update_fields=["item_custom_field_defs"])
    make_product(tenant_a.company, sku="V1", name="One", custom_fields={"brandCode": "ACME"})

    calls = {"n": 0}
    original = custom_fields_module.distinct_values_for_keys

    def _counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(custom_fields_module, "distinct_values_for_keys", _counting)

    first = tenant_a.client.get("/api/v1/products/custom-field-values/")
    assert first.status_code == 200, first.data
    assert first.data.get("brandCode") == ["ACME"]
    assert calls["n"] == 1

    second = tenant_a.client.get("/api/v1/products/custom-field-values/")
    assert second.status_code == 200, second.data
    assert second.data.get("brandCode") == ["ACME"]
    assert calls["n"] == 1, "second call should have hit the cache, not re-scanned products"


def test_b8_027_custom_field_values_cache_is_scoped_per_company(tenant_b):
    """A second company must not see -- or share a cache key with -- the
    first company's distinct values."""
    tenant_b.company.item_custom_field_defs = [
        {"key": "brandCode", "label": "Brand code", "type": "list", "active": True, "options": []},
    ]
    tenant_b.company.save(update_fields=["item_custom_field_defs"])
    make_product(tenant_b.company, sku="V1", name="One", custom_fields={"brandCode": "OTHERCO"})

    resp = tenant_b.client.get("/api/v1/products/custom-field-values/")
    assert resp.status_code == 200, resp.data
    assert resp.data.get("brandCode") == ["OTHERCO"]
