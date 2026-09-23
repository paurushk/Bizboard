"""COMP-006 buyer GSTIN checks inside build_gst_health."""

import inspect
from decimal import Decimal

import pytest
from django.utils import timezone

from core.services.gstin_verify import GstinLookupResult
from core.validators import validate_gstin
from reporting import gst_health
from reporting.gst_health import build_gst_health
from sales.models import SalesInvoice
from tests.conftest import make_customer

VALID_GSTIN = "29AAAAA0000A1ZY"
BAD_CHECKSUM = "29AAAAA0000A1Z6"


def _enable(company):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_GST_GUARD"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _invoice(company, customer, *, number, invoice_type="GST", party_gstin=""):
    return SalesInvoice.objects.create(
        company=company,
        customer=customer,
        number=number,
        status=SalesInvoice.Status.COMPLETED,
        invoice_type=invoice_type,
        invoice_date=timezone.localdate(),
        filing_party_gstin=party_gstin,
        taxable_total=Decimal("100"),
        grand_total=Decimal("100"),
    )


def _codes(company, invoice_id):
    health = build_gst_health(company)
    return {
        a["code"]
        for a in health["alerts"]
        if a.get("document_id") == invoice_id and a["code"] in {"GSTIN_FORMAT_INVALID", "GSTIN_INACTIVE"}
    }


def test_no_duplicate_invoice_check_in_gst_health():
    src = inspect.getsource(gst_health)
    assert "DUPLICATE_INVOICE" not in src
    assert "financial_year" not in src


def test_valid_gstin_constant_passes_checksum():
    validate_gstin(VALID_GSTIN)


@pytest.mark.django_db
def test_blank_buyer_gstin_is_skipped(tenant_a):
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin="")
    inv = _invoice(tenant_a.company, customer, number="GG-BLANK", party_gstin="")
    assert _codes(tenant_a.company, inv.id) == set()


@pytest.mark.django_db
def test_bad_checksum_alerts_and_does_not_call_provider(tenant_a, monkeypatch):
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin="")

    def boom(_gstin):
        raise AssertionError("provider must not be called for a format failure")

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", boom)
    inv = _invoice(tenant_a.company, customer, number="GG-BAD", party_gstin=BAD_CHECKSUM)
    alerts = [
        a for a in build_gst_health(tenant_a.company)["alerts"]
        if a.get("document_id") == inv.id and a["code"] == "GSTIN_FORMAT_INVALID"
    ]
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["document_type"] == "sales_invoice"
    assert inv.number in alerts[0]["message"]


@pytest.mark.django_db
def test_flag_off_does_not_alert(tenant_a):
    customer = make_customer(tenant_a.company, gstin="")
    inv = _invoice(tenant_a.company, customer, number="GG-OFF", party_gstin=BAD_CHECKSUM)
    assert _codes(tenant_a.company, inv.id) == set()


@pytest.mark.django_db
@pytest.mark.parametrize("provider_status", ["INVALID", "CANCELLED", "SUSPENDED"])
def test_inactive_buyer_gstin_alerts(tenant_a, monkeypatch, provider_status):
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN)

    class Live:
        def lookup(self, gstin):
            return GstinLookupResult(
                gstin=gstin, legal_name="", status=provider_status,
                state_code="29", taxpayer_type="", raw={},
            )

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", lambda: Live())
    inv = _invoice(tenant_a.company, customer, number=f"GG-{provider_status}", party_gstin=VALID_GSTIN)
    alerts = [
        a for a in build_gst_health(tenant_a.company)["alerts"]
        if a.get("document_id") == inv.id and a["code"] == "GSTIN_INACTIVE"
    ]
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    assert provider_status in alerts[0]["message"]


@pytest.mark.django_db
def test_unverified_and_null_provider_skip(tenant_a, monkeypatch, caplog):
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN)
    inv = _invoice(tenant_a.company, customer, number="GG-NULL", party_gstin=VALID_GSTIN)
    assert _codes(tenant_a.company, inv.id) == set()
    assert "no live provider" in caplog.text

    class Unverified:
        def lookup(self, gstin):
            return GstinLookupResult(
                gstin=gstin, legal_name="", status="UNVERIFIED",
                state_code="29", taxpayer_type="", raw={},
            )

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", lambda: Unverified())
    inv2 = _invoice(tenant_a.company, customer, number="GG-UNV", party_gstin=VALID_GSTIN)
    assert _codes(tenant_a.company, inv2.id) == set()
    assert "UNVERIFIED" in caplog.text


@pytest.mark.django_db
def test_retail_is_included_non_gst_is_not(tenant_a):
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin="")
    retail = _invoice(
        tenant_a.company, customer, number="GG-RET", invoice_type="RETAIL", party_gstin=BAD_CHECKSUM,
    )
    non_gst = _invoice(
        tenant_a.company, customer, number="GG-NG", invoice_type="NON_GST", party_gstin=BAD_CHECKSUM,
    )
    assert "GSTIN_FORMAT_INVALID" in _codes(tenant_a.company, retail.id)
    assert _codes(tenant_a.company, non_gst.id) == set()


@pytest.mark.django_db
@pytest.mark.parametrize("provider_status", ["VALID", ""])
def test_unrecognized_or_valid_status_does_not_alert(tenant_a, monkeypatch, provider_status):
    """A status outside {INVALID, CANCELLED, SUSPENDED, UNVERIFIED} — a
    genuinely VALID GSTIN, or an unrecognized/empty status from a future
    GST-portal status code — must fall through to no alert, not raise or
    mis-classify as inactive.
    """
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN)

    class Live:
        def lookup(self, gstin):
            return GstinLookupResult(
                gstin=gstin, legal_name="", status=provider_status,
                state_code="29", taxpayer_type="", raw={},
            )

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", lambda: Live())
    inv = _invoice(tenant_a.company, customer, number=f"GG-STATUS-{provider_status or 'EMPTY'}", party_gstin=VALID_GSTIN)
    assert _codes(tenant_a.company, inv.id) == set()


@pytest.mark.django_db
def test_flag_off_also_suppresses_the_live_lookup_branch(tenant_a, monkeypatch):
    """test_flag_off_does_not_alert only exercises a format-invalid GSTIN,
    which short-circuits before the flag would matter for the live-lookup
    branch specifically. This proves the flag being off also skips the live
    provider call entirely for a format-valid GSTIN that would otherwise
    alert as GSTIN_INACTIVE.
    """
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN)

    def boom():
        raise AssertionError("provider must not be called when ENABLE_GST_GUARD is off")

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", boom)
    inv = _invoice(tenant_a.company, customer, number="GG-FLAGOFF-LIVE", party_gstin=VALID_GSTIN)
    assert _codes(tenant_a.company, inv.id) == set()


@pytest.mark.django_db
def test_live_provider_called_once_per_unique_buyer_gstin(tenant_a, monkeypatch):
    """F1-006: confirms the per-run cache (gst_health.py's buyer_gstin_cache)
    actually prevents N+1 live lookups, not just that the cache dict exists —
    two invoices sharing the same buyer GSTIN in one build_gst_health() run
    must trigger exactly one provider.lookup() call.
    """
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN)
    calls = {"count": 0}

    class Counting:
        def lookup(self, gstin):
            calls["count"] += 1
            return GstinLookupResult(
                gstin=gstin, legal_name="", status="VALID",
                state_code="29", taxpayer_type="", raw={},
            )

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", lambda: Counting())
    _invoice(tenant_a.company, customer, number="GG-CACHE-1", party_gstin=VALID_GSTIN)
    _invoice(tenant_a.company, customer, number="GG-CACHE-2", party_gstin=VALID_GSTIN)
    build_gst_health(tenant_a.company)
    assert calls["count"] == 1


@pytest.mark.django_db
def test_invalid_format_buyer_gstin_reaches_today_via_business_alerts(tenant_a):
    """The Attention-page path is covered by
    test_critical_buyer_gstin_becomes_a_named_attention_row; this covers the
    separate Today/insights-alerts path (GST_HEALTH_CRITICAL_OPEN), which
    nothing previously exercised for these two new checks specifically.
    """
    from insights.alerts import build_business_alerts

    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin="")
    _invoice(tenant_a.company, customer, number="GG-TODAY", party_gstin=BAD_CHECKSUM)
    rows = [a for a in build_business_alerts(tenant_a.company) if a["code"] == "GST_HEALTH_CRITICAL_OPEN"]
    assert len(rows) == 1


@pytest.mark.django_db
def test_critical_buyer_gstin_becomes_a_named_attention_row(tenant_a):
    from insights.attention import _itc_and_gst_rows

    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin="")
    inv = _invoice(tenant_a.company, customer, number="GG-ATTN", party_gstin=BAD_CHECKSUM)
    rows = [
        row for row in _itc_and_gst_rows(tenant_a.company, timezone.localdate())
        if row["code"] == "GST_GUARDRAIL" and row["entity_ref"]["id"] == inv.id
    ]
    assert len(rows) == 1
    assert rows[0]["entity_ref"]["type"] == "sales_invoice"
    assert rows[0]["action_href"] == f"/sales/history/{inv.id}"
    assert "GG-ATTN" in rows[0]["title"]


@pytest.mark.django_db
def test_gst_guard_log_records_format_check_and_skipped_active_status(tenant_a, caplog):
    import logging

    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, gstin=VALID_GSTIN)
    _invoice(tenant_a.company, customer, number="GG-LOG", party_gstin=VALID_GSTIN)
    with caplog.at_level(logging.INFO, logger="bizboard.flags"):
        assert _codes(tenant_a.company, SalesInvoice.objects.get(number="GG-LOG").id) == set()
    assert "check=format" in caplog.text
    assert "active_status=skipped" in caplog.text
    assert f"tenant_id={tenant_a.company.id}" in caplog.text
