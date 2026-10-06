"""GST health and the document series share resolve_series_gstin. Sequences stay put."""

import pytest
from django.utils import timezone

from accounts.models import Company, CompanyGstin
from core.services.document_numbers import DocumentNumberService
from reporting.gst_health import build_gst_health

pytestmark = pytest.mark.django_db

STAMP = "29ABCDE1234F1ZW"
OTHER = "27AAAAA0000A1Z5"


def _codes(company):
    return {alert["code"] for alert in build_gst_health(company)["alerts"]}


def _peek(company):
    return DocumentNumberService.peek(company, "SALES_INVOICE")


def test_stamp_only_company_is_not_missing_and_does_not_renumber(tenant_a):
    company = tenant_a.company
    Company.objects.filter(pk=company.pk).update(gstin="", registration_type=Company.RegistrationType.REGULAR)
    company.refresh_from_db()
    CompanyGstin.objects.create(
        company=company, gstin=STAMP, state="Karnataka", is_primary=False, is_active=True,
    )
    company.refresh_from_db()
    assert company.gstin == ""

    before = _peek(company)
    assert before["gstin_key"] == STAMP
    assert before["prefix"].endswith(STAMP[-4:])
    codes = _codes(company)
    after = _peek(company)
    assert after["prefix"] == before["prefix"]
    assert after["gstin_key"] == before["gstin_key"]
    assert after["next_number"] == before["next_number"]
    assert "GSTIN_MISSING_COMPANY" not in codes
    assert "GSTIN_UNVERIFIED" not in codes

    me = tenant_a.client.get("/api/v1/auth/me/")
    assert me.status_code == 200
    payload = me.data.get("data") or me.data
    assert payload["company"]["gstin"] == ""
    assert payload["company"]["series_gstin"] == STAMP


def test_head_office_gstin_keeps_format_and_verification_checks(tenant_a):
    company = tenant_a.company
    Company.objects.filter(pk=company.pk).update(
        gstin=STAMP,
        registration_type=Company.RegistrationType.REGULAR,
        gstin_verification_status="VALID",
        gstin_verified_at=timezone.now(),
    )
    company.refresh_from_db()
    assert not CompanyGstin.objects.filter(company=company).exists()
    peeked = _peek(company)
    assert peeked["gstin_key"] == STAMP
    assert "GSTIN_MISSING_COMPANY" not in _codes(company)
    assert "GSTIN_UNVERIFIED" not in _codes(company)

    Company.objects.filter(pk=company.pk).update(gstin_verification_status="UNVERIFIED")
    company.refresh_from_db()
    assert "GSTIN_UNVERIFIED" in _codes(company)

    Company.objects.filter(pk=company.pk).update(gstin="BADGSTINVALUE1")
    company.refresh_from_db()
    assert "GSTIN_INVALID_FORMAT" in _codes(company)


def test_both_gstins_differ_series_follows_stamp_not_head_office(tenant_a):
    company = tenant_a.company
    CompanyGstin.objects.create(
        company=company, gstin=STAMP, state="Karnataka", is_primary=True, is_active=True,
    )
    Company.objects.filter(pk=company.pk).update(
        gstin=OTHER, registration_type=Company.RegistrationType.REGULAR,
    )
    company.refresh_from_db()
    assert company.gstin == OTHER
    before = _peek(company)
    assert before["gstin_key"] == STAMP
    assert before["gstin_key"] != OTHER
    codes = _codes(company)
    after = _peek(company)
    assert after["next_number"] == before["next_number"]
    assert after["prefix"] == before["prefix"]
    assert "GSTIN_MISSING_COMPANY" not in codes
    assert "GSTIN_UNVERIFIED" not in codes


def test_neither_gstin_is_missing_and_prefix_has_no_stamp_suffix(tenant_a):
    company = tenant_a.company
    Company.objects.filter(pk=company.pk).update(
        gstin="", registration_type=Company.RegistrationType.REGULAR,
    )
    company.refresh_from_db()
    CompanyGstin.objects.filter(company=company).delete()
    peeked = _peek(company)
    assert peeked["gstin_key"] == ""
    assert STAMP[-4:] not in peeked["prefix"]
    assert "GSTIN_MISSING_COMPANY" in _codes(company)


def test_unregistered_company_has_no_gstin_alerts(tenant_a):
    company = tenant_a.company
    Company.objects.filter(pk=company.pk).update(
        gstin="", registration_type=Company.RegistrationType.UNREGISTERED,
    )
    company.refresh_from_db()
    assert "GSTIN_MISSING_COMPANY" not in _codes(company)
    assert "GSTIN_INVALID_FORMAT" not in _codes(company)
    assert "GSTIN_UNVERIFIED" not in _codes(company)
