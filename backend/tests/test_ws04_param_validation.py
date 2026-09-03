"""WS-04 — bad client input returns HTTP 400, not a 500.

Findings B7-009, B7-010, B9-018, B9-019.
"""
from __future__ import annotations

from datetime import date
from decimal import InvalidOperation

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


def test_validate_gst_rate_non_numeric_raises_validationerror():
    from core.validators import validate_gst_rate

    with pytest.raises(ValidationError):
        validate_gst_rate("abc")  # B7-009: not decimal.InvalidOperation -> 500
    with pytest.raises(ValidationError):
        validate_gst_rate(None)
    # a real allowed rate still passes
    validate_gst_rate("18")


def test_document_tax_date_tolerates_malformed_string():
    from core.services.billing import _document_tax_date

    class _Doc:
        invoice_date = "01/02/2026"  # non-ISO -> used to raise ValueError

    assert _document_tax_date(_Doc()) is None  # B7-010

    class _Doc2:
        invoice_date = "2026-02-01"

    assert _document_tax_date(_Doc2()) == date(2026, 2, 1)


def test_checkout_rejects_non_numeric_plan_id(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/billing/checkout/", {"plan_id": "not-a-number"}, format="json"
    )
    assert resp.status_code == 400, resp.data  # B9-018: was a 500


def test_lead_convert_rejects_non_decimal_amount(tenant_a):
    lead = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Prospect", "phone": "9876500000", "status": "NEW"},
        format="json",
    )
    lead_id = (lead.data.get("data") or lead.data)["id"]
    resp = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/convert/", {"amount": "abc"}, format="json"
    )
    assert resp.status_code == 400, resp.data  # B9-019: was a 500

    # a valid amount still works
    ok = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/convert/", {"amount": "1500.50"}, format="json"
    )
    assert ok.status_code == 200, ok.data


def test_invalid_operation_not_raised_from_validators():
    """Guard against a regression to the raw Decimal() call."""
    from core.validators import validate_gst_rate

    try:
        validate_gst_rate("%%%")
    except ValidationError:
        pass
    except InvalidOperation:  # pragma: no cover
        pytest.fail("validate_gst_rate leaked decimal.InvalidOperation")
