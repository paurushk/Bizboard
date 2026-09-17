"""§H3 — a failed async task surfaces as user-visible state, never a silent
hang or a 500. (Celery runs eager in tests, so the task body executes inline.)

``test_failed_invoice_pdf_ends_FAILED_and_is_recoverable`` is the retry →
user-visible-state proof (FAILED on pdf-status, then regenerate → READY).
Beat-schedule dry-run lives in ``test_ops_contracts.test_every_beat_task_dry_runs_eager``.
Does not close G-10 (real broker).
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_failed_invoice_pdf_ends_FAILED_and_is_recoverable(tenant_a):
    from sales.models import SalesInvoice

    product = make_product(tenant_a.company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, state="Karnataka", gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    iid = inv["id"]

    # PDF renderer blows up during the (eager) post-complete task.
    # sales/tasks.py does `from .pdf import render_gst_tax_invoice`, so patch it
    # on the `sales.pdf` package namespace.
    with mock.patch(
        "sales.pdf.render_gst_tax_invoice", side_effect=RuntimeError("boom")
    ):
        done = tenant_a.client.post(f"/api/v1/sales/invoices/{iid}/complete/")
    # the invoice itself still completes — billing never waits on rendering
    assert done.status_code == 200, done.data

    status = tenant_a.client.get(f"/api/v1/sales/invoices/{iid}/pdf-status/")
    assert status.status_code == 200
    assert status.data["pdf_status"] == SalesInvoice.PdfStatus.FAILED
    assert status.data["pdf_file"] is None

    # downloading a not-ready PDF is a clean 4xx, not a 500
    dl = tenant_a.client.get(f"/api/v1/sales/invoices/{iid}/pdf/")
    assert dl.status_code in (404, 409, 425, 400)

    # regenerate succeeds once the transient fault clears -> READY
    regen = tenant_a.client.post(f"/api/v1/sales/invoices/{iid}/regenerate-pdf/")
    assert regen.status_code == 200, regen.data
    final = tenant_a.client.get(f"/api/v1/sales/invoices/{iid}/pdf-status/")
    assert final.data["pdf_status"] == SalesInvoice.PdfStatus.READY
    assert final.data["pdf_file"] is not None
