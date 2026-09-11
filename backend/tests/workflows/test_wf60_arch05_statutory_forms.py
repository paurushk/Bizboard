"""WF-60 / D15 / QOS-0027 — ARCH-05 statutory compliance (drug licence
20B/21B, FSSAI).

A DRUG/FOOD-regulated invoice line -> Complete soft-blocks with no active
company licence on file -> add the licence via the API -> Complete succeeds
-> the GST invoice PDF prints the licence number and the batch/expiry
snapshot already captured on the line.

No-op unless `ENABLE_ARCH05_STATUTORY_FORMS` is on; every other archetype's
Complete path is untouched (see tests/personas/ and the other WF chains,
which all run with the flag at its default OFF).

Mirrors BUSINESS_ARCHETYPES_AND_PERSONAS.md section 8/13 (ARCH-05).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.test import override_settings
from pypdf import PdfReader

from core.help_codes import HelpCode
from sales.models import SalesInvoice
from sales.pdf import render_gst_tax_invoice
from tests.conftest import create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


@override_settings(ENABLE_ARCH05_STATUTORY_FORMS=True)
def test_wf60_arch05_drug_licence_soft_block_then_pdf(tenant_a, assert_consistent):
    company = tenant_a.company
    company.accounting_enabled = True
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.save()
    client = tenant_a.client

    # --------------------------------------------------------- 1. regulated product
    tablet = make_product(
        company, sku="TAB-500", gst_rate="12", purchase_price="40", selling_price="60",
        regulated_category="DRUG", track_batch=True,
    )
    batch_no, exp_date = "BN-2201", (date.today() + timedelta(days=180)).isoformat()
    opening = client.post("/api/v1/inventory/opening-stock/", {
        "product": tablet.id, "quantity": "100", "unit_cost": "40",
        "batch_no": batch_no, "expiry_date": exp_date,
    }, format="json")
    assert opening.status_code == 201, opening.data

    customer = make_customer(company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": tablet.id, "quantity": "10", "unit_price": "60"}],
    )

    # ---------------------------------------------- 2. Complete soft-blocks: no licence
    blocked = client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert blocked.status_code == 400, blocked.data
    assert blocked.data["error"]["code"] == HelpCode.CONFIRM_MISSING_LICENCE

    # ------------------------------------------------------- 3. add the licence
    licence = client.post("/api/v1/company/statutory-licences/", {
        "licence_type": "DRUG_20B", "licence_number": "MH-DL-20B-99887",
        "premises_state": "Karnataka", "is_active": True,
    }, format="json")
    assert licence.status_code == 201, licence.data

    # ------------------------------------------------------- 4. Complete now succeeds
    done = client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    assert Decimal(str(done.data["grand_total"])) == Decimal("672.00")  # 600 + 12% GST

    # ------------------------------------------------- 5. PDF carries both declarations
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    text = _pdf_text(render_gst_tax_invoice(invoice, copy="ORIGINAL"))
    assert "MH-DL-20B-99887" in text
    assert batch_no in text

    # ---------------------------------------------------------- 6. whole-chain check
    assert_consistent(company)


@override_settings(ENABLE_ARCH05_STATUTORY_FORMS=True)
def test_wf60_confirm_override_completes_without_a_licence(tenant_a, assert_consistent):
    company = tenant_a.company
    company.state = "Karnataka"
    company.save()
    client = tenant_a.client

    tablet = make_product(
        company, sku="TAB-501", gst_rate="12", selling_price="60", regulated_category="DRUG",
    )
    client.post("/api/v1/inventory/opening-stock/", {
        "product": tablet.id, "quantity": "10", "unit_cost": "40",
    }, format="json")
    customer = make_customer(company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": tablet.id, "quantity": "1", "unit_price": "60"}],
    )

    done = client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/", {"confirm_missing_licence": True},
        format="json",
    )
    assert done.status_code == 200, done.data
    assert_consistent(company)
