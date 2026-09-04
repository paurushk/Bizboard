"""Remaining backlog: GSTR worksheets, GSTN JSON, bank CSV, FY series, FIU fail-closed."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from banking.fiu_adapter import fetch_live_transactions_for_consent
from core.exceptions import BusinessRuleError
from core.services.document_numbers import DocumentNumberService
from core.services.identity_verify import HttpIdentityProvider, get_identity_provider
from payments.recon import parse_bank_csv
from reporting.gst_returns import build_gstr1, build_gstr9, to_gstn_json
from reporting.models import Gstr2bIngest

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "bank"


def test_bank_csv_presets_parse_sample_fixtures():
    hdfc, _ = parse_bank_csv((FIXTURES / "hdfc_sample.csv").read_text(encoding="utf-8"), preset="hdfc")
    icici, _ = parse_bank_csv((FIXTURES / "icici_sample.csv").read_text(encoding="utf-8"), preset="icici")
    sbi, _ = parse_bank_csv((FIXTURES / "sbi_sample.csv").read_text(encoding="utf-8"), preset="sbi")
    assert len(hdfc) == 2
    assert hdfc[0]["amount"] == Decimal("15000.00")
    assert hdfc[1]["amount"] == Decimal("-8000.00")
    assert len(icici) == 2
    assert icici[0]["amount"] == Decimal("12500.50")
    assert len(sbi) == 2
    assert sbi[0]["utr"]


def test_gstr9_table_8_is_worksheet_not_stub(tenant_a):
    Gstr2bIngest.objects.create(
        company=tenant_a.company,
        period="2026-04",
        supplier_gstin="29AAAAA0000A1Z5",
        invoice_number="PIN-1",
        taxable_value=Decimal("1000"),
        igst=Decimal("180"),
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        itc_eligibility=Gstr2bIngest.ItcEligibility.CLAIMABLE,
        raw={"source": "2B"},
    )
    payload = build_gstr9(tenant_a.company, "2026-27")
    table8 = payload["tables"]["8"]
    assert table8["aid_kind"] == "itc_2b_vs_books_fy"
    assert Decimal(table8["itc_as_per_2b"]) == Decimal("180.00")
    assert "portal" not in (payload.get("disclaimer") or "").lower() or "not" in payload["disclaimer"].lower()


def test_gstr1_supecom_has_table_15_buckets(tenant_a):
    payload = build_gstr1(tenant_a.company, "2026-08")
    supecom = payload["supecom"]
    assert supecom["table"] == "15"
    assert "15A" in supecom and "15B" in supecom
    assert isinstance(supecom["15A"], list)


def test_gstr8_is_honest_stub(tenant_a):
    from reporting.gstr2b import build_gstr8

    payload = build_gstr8(tenant_a.company, "2026-08")
    assert payload["supported"] is False
    assert "not implement" in payload["disclaimer"].lower() or "stub" in payload["disclaimer"].lower()



def test_gstn_json_mapper_is_not_a_portal_file(tenant_a):
    payload = build_gstr1(tenant_a.company, "2026-08")
    shaped = to_gstn_json(payload)
    assert shaped["fp"] == "082026"
    assert "not a GSTN portal upload" in shaped["disclaimer"]
    assert "b2b" in shaped


def test_fy_series_when_gstin_resolved(tenant_a):
    n = DocumentNumberService.next_number(
        tenant_a.company,
        "SALES_INVOICE",
        gstin="29ABCDE1234F1ZW",
        on_date=date(2026, 8, 21),
    )
    assert "2627" in n


def test_live_fiu_fail_closed_without_url():
    with pytest.raises(BusinessRuleError):
        fetch_live_transactions_for_consent(consent_id="c1", fi_type="DEPOSIT")


def test_identity_http_without_endpoint_stays_unverified():
    provider = get_identity_provider()
    assert provider.__class__.__name__ == "NullIdentityProvider"
    http = HttpIdentityProvider()
    result = http.lookup_pan("AAAPA1234A")
    assert result.status == "UNVERIFIED"
    assert result.raw.get("provider") == "http"


def test_gstn_json_disabled_in_production_helper():
    from django.test.utils import override_settings as _os
    from reporting.views import _maybe_gstn_json

    class Req:
        query_params = {"format": "gstn-json"}

    with _os(DJANGO_ENV="production", ENABLE_GSTN_JSON=False):
        with pytest.raises(BusinessRuleError):
            _maybe_gstn_json(Req(), {"return_type": "GSTR-1", "period": "2026-08"})
