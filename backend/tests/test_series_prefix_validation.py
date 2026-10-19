"""SET-02: a series prefix is validated, never silently truncated or replaced."""

import pytest

from core.services.document_numbers import DocumentNumberService

URL = "/api/v1/sales/invoices/number-series/"


@pytest.mark.parametrize("prefix", ["INV", "SI", "INV-2627-F1Z5", "A/B-1", "inv2627", " INV "])
def test_valid_prefix_is_accepted(prefix):
    assert DocumentNumberService.validate_prefix(prefix) == prefix.strip()


@pytest.mark.parametrize(
    "prefix",
    ["", "   ", "—", "INV 01", "INV_01", "-INV", "INV-", "/INV", "INV/", "A" * 17, "IN€V"],
)
def test_bad_prefix_is_refused(prefix):
    with pytest.raises(ValueError):
        DocumentNumberService.validate_prefix(prefix)


def test_over_long_prefix_is_refused_not_cut(tenant_a):
    before = DocumentNumberService.peek(tenant_a.company, "SALES_INVOICE")["prefix"]
    r = tenant_a.client.patch(URL, {"prefix": "ABCDEFGHIJKLMNOPQ"}, format="json")
    assert r.status_code == 400, r.data
    assert DocumentNumberService.peek(tenant_a.company, "SALES_INVOICE")["prefix"] == before


def test_placeholder_dash_prefix_cannot_be_saved(tenant_a):
    before = DocumentNumberService.peek(tenant_a.company, "SALES_INVOICE")["prefix"]
    r = tenant_a.client.patch(URL, {"prefix": "—", "next_number": 1}, format="json")
    assert r.status_code == 400, r.data
    assert DocumentNumberService.peek(tenant_a.company, "SALES_INVOICE")["prefix"] == before


def test_good_prefix_still_saves(tenant_a):
    r = tenant_a.client.patch(URL, {"prefix": "SI", "padding": 6}, format="json")
    assert r.status_code == 200, r.data
    assert DocumentNumberService.peek(tenant_a.company, "SALES_INVOICE")["prefix"] == "SI"
