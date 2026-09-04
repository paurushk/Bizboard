"""WS-11 — GST/tax export & report correctness (review B5-002, B5-012, B5-015)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import create_draft_purchase, make_supplier
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db


def test_tds_worksheet_csv_escapes_formula_in_supplier_name(books):
    """B5-002: a supplier named with a leading '=' must not execute in Excel."""
    supplier = make_supplier(books.company, name="=cmd|' /C calc'!A1")
    from masters.models import Product

    product = Product.objects.create(
        company=books.company, name="Svc", sku="SVC-1",
        purchase_price=Decimal("1000"), selling_price=Decimal("1000"),
        gst_rate=Decimal("0"), created_by=books.owner, updated_by=books.owner,
    )
    draft = create_draft_purchase(
        books, supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    books.client.patch(
        f"/api/v1/purchases/invoices/{draft['id']}/",
        {"tdsSection": "194C", "tdsRate": "1", "tdsAmount": "10.00", "invoiceDate": "2026-08-05"},
        format="json",
    )
    assert books.client.post(
        f"/api/v1/purchases/invoices/{draft['id']}/complete/"
    ).status_code == 200

    resp = books.client.get("/api/v1/reports/tds-worksheet/", {"period": "2026-08"})
    assert resp.status_code == 200

    import csv as _csv
    import io as _io

    reader = _csv.reader(_io.StringIO(resp.content.decode()))
    supplier_cells = [
        cell for row in reader for cell in row if "calc" in cell and "cmd" in cell
    ]
    assert supplier_cells, "supplier name row not found in the worksheet CSV"
    for cell in supplier_cells:
        assert cell.startswith("'"), f"formula not neutralised: {cell!r}"
