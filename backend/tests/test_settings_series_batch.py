"""SET-02: all series in one call, GSTIN and financial-year selection, all-or-nothing save, optimistic lock."""

from datetime import timedelta

from core.models import DocumentSeries

URL = "/api/v1/company/number-series/"


def _items(response):
    return {i["doc_type"]: i for i in response.data["items"]}


def test_lists_every_series_with_preview_and_options(tenant_a):
    r = tenant_a.client.get(URL)
    assert r.status_code == 200, r.data
    items = _items(r)
    assert len(items) == 11 and "SALES_INVOICE" in items and "GOODS_RECEIPT" in items
    row = items["SALES_INVOICE"]
    assert row["preview"].endswith(f"{row['next_number']:0{row['padding']}d}")
    assert row["updated_at"]
    assert r.data["fy_options"] and isinstance(r.data["gstins"], list)


def test_owner_only(tenant_a):
    assert tenant_a.staff_client.get(URL).status_code == 403
    assert tenant_a.staff_client.patch(URL, {"items": []}, format="json").status_code == 403


def test_saves_several_series_together(tenant_a):
    r = tenant_a.client.patch(
        URL,
        {"items": [
            {"doc_type": "SALES_INVOICE", "prefix": "TAX", "padding": 4},
            {"doc_type": "QUOTATION", "prefix": "EST", "next_number": 50},
        ]},
        format="json",
    )
    assert r.status_code == 200, r.data
    items = _items(r)
    assert items["SALES_INVOICE"]["prefix"] == "TAX" and items["SALES_INVOICE"]["padding"] == 4
    assert items["QUOTATION"]["prefix"] == "EST" and items["QUOTATION"]["next_number"] == 50


def test_one_bad_row_saves_nothing_and_names_the_row(tenant_a):
    before = _items(tenant_a.client.get(URL))
    r = tenant_a.client.patch(
        URL,
        {"items": [
            {"doc_type": "SALES_INVOICE", "prefix": "GOOD"},
            {"doc_type": "QUOTATION", "prefix": "bad prefix!"},
        ]},
        format="json",
    )
    assert r.status_code == 400, r.data
    assert "QUOTATION" in str(r.data)
    after = _items(tenant_a.client.get(URL))
    assert after["SALES_INVOICE"]["prefix"] == before["SALES_INVOICE"]["prefix"]


def test_stale_row_is_refused_with_409_and_nothing_changes(tenant_a):
    first = _items(tenant_a.client.get(URL))["QUOTATION"]
    DocumentSeries.objects.filter(company=tenant_a.company, doc_type="QUOTATION").update(
        prefix="OTHER", updated_at=DocumentSeries.objects.get(company=tenant_a.company, doc_type="QUOTATION").updated_at
        + timedelta(seconds=5)
    )
    r = tenant_a.client.patch(
        URL,
        {"items": [{"doc_type": "QUOTATION", "prefix": "MINE", "expected_updated_at": first["updated_at"]}]},
        format="json",
    )
    assert r.status_code == 409, r.data
    assert DocumentSeries.objects.get(company=tenant_a.company, doc_type="QUOTATION").prefix == "OTHER"


def test_current_updated_at_is_accepted(tenant_a):
    row = _items(tenant_a.client.get(URL))["QUOTATION"]
    r = tenant_a.client.patch(
        URL,
        {"items": [{"doc_type": "QUOTATION", "prefix": "MINE", "expected_updated_at": row["updated_at"]}]},
        format="json",
    )
    assert r.status_code == 200, r.data


def test_allocating_a_number_does_not_make_the_form_stale(tenant_a):
    from django.db import transaction

    from core.services.document_numbers import DocumentNumberService

    row = _items(tenant_a.client.get(URL))["QUOTATION"]
    with transaction.atomic():
        DocumentNumberService.next_number(tenant_a.company, "QUOTATION")
    r = tenant_a.client.patch(
        URL,
        {"items": [{"doc_type": "QUOTATION", "prefix": "EST", "expected_updated_at": row["updated_at"]}]},
        format="json",
    )
    assert r.status_code == 200, r.data


def test_long_invoice_number_warns_but_still_saves(tenant_a):
    r = tenant_a.client.patch(
        URL,
        {"items": [{"doc_type": "SALES_INVOICE", "prefix": "ABCDEFGHIJKLMNOP", "padding": 8}]},
        format="json",
    )
    assert r.status_code == 200, r.data
    row = _items(r)["SALES_INVOICE"]
    assert row["length"] > 16 and "16" in row["length_warning"]
    assert _items(r)["QUOTATION"]["length_warning"] is None


def test_financial_year_selection_keeps_each_year_separate(tenant_a):
    this_year = tenant_a.client.get(URL).data
    other = "2019-20"
    r = tenant_a.client.patch(
        URL, {"fy": other, "items": [{"doc_type": "SALES_INVOICE", "prefix": "OLD"}]}, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["fy_label"] == other
    assert _items(tenant_a.client.get(URL))["SALES_INVOICE"]["prefix"] == _items(
        type("R", (), {"data": this_year})()
    )["SALES_INVOICE"]["prefix"]
    assert tenant_a.client.get(URL, {"fy": "2019-21"}).status_code == 400


def test_unknown_gstin_and_document_type_are_refused(tenant_a):
    assert tenant_a.client.get(URL, {"gstin": "29ABCDE1234F1ZW"}).status_code == 400
    r = tenant_a.client.patch(URL, {"items": [{"doc_type": "NOPE", "prefix": "X"}]}, format="json")
    assert r.status_code == 400
