"""PJ-SERIALIZED — ARCH-06 High-Value Serialized Goods Dealer Journey.

Validates:
1. Unit serial number tracking for electronics/appliances (track_serial=True).
2. Serial lifecycle progression: AVAILABLE -> SOLD -> AVAILABLE (on return).
3. Outward sale with serial validation (cannot sell non-existent or already-sold serial).
4. Return validation and warranty fraud prevention (duplicate returns rejected).
5. Persona capability and visibility boundaries across Staff, Custodian, Accountant, and Owner.
6. Clean invariant sweeps across all operations.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from inventory.models import MovementType, SerialNumber
from inventory.services import InventoryService
from sales.models import SalesReturn
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_serialized_lifecycle_and_warranty_fraud_guard(boundary):
    ns = seed_archetype("serialized")
    company = ns.company
    oc = ns.owner_client
    sc = ns.sales_client
    gc = ns.godown_client
    ac = ns.acct_client
    product = ns.products[0]
    cust = ns.customers[0]
    wh = ns.warehouses[0]

    assert product.track_serial is True

    # 1. P4 Godown Custodian registers serialized inventory
    sn1 = SerialNumber.objects.create(
        company=company, product=product, warehouse=wh, serial_number="SN-PHONE-001",
        status=SerialNumber.Status.AVAILABLE,
    )
    sn2 = SerialNumber.objects.create(
        company=company, product=product, warehouse=wh, serial_number="SN-PHONE-002",
        status=SerialNumber.Status.AVAILABLE,
    )

    InventoryService.post_movement(
        company=company, warehouse=wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("2"), unit_cost=Decimal("60.00"),
        user=ns.godown,
    )

    assert InventoryService.available_quantity(company, product, wh) == Decimal("2.000")
    assert SerialNumber.objects.get(pk=sn1.pk).status == SerialNumber.Status.AVAILABLE
    assert SerialNumber.objects.get(pk=sn2.pk).status == SerialNumber.Status.AVAILABLE

    # 2. P2 Sales Staff sells unit SN-PHONE-001
    inv = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18",
                    "serial_numbers": ["SN-PHONE-001"],
                },
            ],
        },
        format="json",
    )
    assert inv.status_code == 201, inv.data
    iid = inv.data["id"]

    complete_resp = sc.post(f"/api/v1/sales/invoices/{iid}/complete/")
    assert complete_resp.status_code == 200, complete_resp.data

    # Serial state transitions to SOLD
    sn1.refresh_from_db()
    assert sn1.status == SerialNumber.Status.SOLD

    # 3. Fraud attempt 1: Try to sell SN-PHONE-001 again on a new invoice
    inv_dupe = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18",
                    "serial_numbers": ["SN-PHONE-001"],
                },
            ],
        },
        format="json",
    )
    if inv_dupe.status_code == 201:
        bad_sale = sc.post(f"/api/v1/sales/invoices/{inv_dupe.data['id']}/complete/")
        assert bad_sale.status_code >= 400, "Selling an already sold serial must fail"
    else:
        assert inv_dupe.status_code >= 400

    # 4. Return workflow: Customer returns SN-PHONE-001
    ret_resp = sc.post(
        "/api/v1/sales/returns/",
        {
            "customer": cust.id,
            "sales_invoice": iid,
            "items": [
                {
                    "product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18",
                    "serial_numbers": ["SN-PHONE-001"],
                },
            ],
        },
        format="json",
    )
    assert ret_resp.status_code == 201, ret_resp.data
    rid = ret_resp.data["id"]

    # Completing a sales return is Owner / cancel-cap (CanCancelDocuments). Sales staff draft the return.
    denied = sc.post(f"/api/v1/sales/returns/{rid}/complete/")
    assert denied.status_code == 403, denied.data
    ret_done = oc.post(f"/api/v1/sales/returns/{rid}/complete/")
    assert ret_done.status_code == 200, ret_done.data

    # Upon sellable return, serial returns to AVAILABLE
    sn1.refresh_from_db()
    assert sn1.status == SerialNumber.Status.AVAILABLE

    # 5. Warranty fraud attempt: Try to return the identical unit a second time
    ret_dupe = sc.post(
        "/api/v1/sales/returns/",
        {
            "customer": cust.id,
            "sales_invoice": iid,
            "items": [
                {
                    "product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18",
                    "serial_numbers": ["SN-PHONE-001"],
                },
            ],
        },
        format="json",
    )
    if ret_dupe.status_code == 201:
        bad_ret = oc.post(f"/api/v1/sales/returns/{ret_dupe.data['id']}/complete/")
        assert bad_ret.status_code != 200, "Duplicate return must be rejected (warranty fraud guard)"
    else:
        assert ret_dupe.status_code >= 400

    # 6. Persona capability boundaries
    # Sales staff cannot cancel invoice; Custodian cannot see P&L; Accountant sees financial reports
    boundary.denied(sc, "post", f"/api/v1/sales/invoices/{iid}/cancel/", data={"reason": "test"}, format="json")
    boundary.denied(gc, "get", "/api/v1/accounting/trial-balance/")
    boundary.allowed(ac, "get", "/api/v1/accounting/trial-balance/")

    assert_all_invariants(company)


def test_pj_bulk_serial_import_partial_failure_blocks_whole_job():
    """G-2 (bulk serial partial-failure ingest) — closes the last open half of
    that gap. There is no standalone "serial import" kind; bulk serial ingest is
    the `opening_serials` sheet on a PRODUCTS import (see
    `imports/services.py::_validate_extra_sheets` and `test_item_godown_expiry.py
    ::test_opening_serials_sheet_posts_serial_opening` for the happy path).

    `_validate_extra_sheets` validates each `opening_serials` row independently
    (unknown SKU / missing serial_no are per-row errors) — but
    `ImportService.commit` is all-or-nothing for PRODUCTS-kind jobs: any
    `error_rows` blocks the ENTIRE commit. So "partial failure" here does not
    mean partial write; it means the one otherwise-valid serial row is *also*
    never posted, and neither is the product itself. This pins that as the
    real, current behavior."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from openpyxl import Workbook

    from masters.models import Product

    ns = seed_archetype("trader")
    ic = ns.importer_client

    wb = Workbook()
    items = wb.active
    items.title = "items"
    items.append(["name", "sku", "gst_rate", "track_serial"])
    items.append(["Bulk Phone", "BULKPH-1", "18", "yes"])
    serials = wb.create_sheet("opening_serials")
    serials.append(["sku", "godown", "serial_no", "as_of", "unit_cost"])
    serials.append(["BULKPH-1", "", "IMEI-OK-1", "", "9000"])   # valid row
    serials.append(["BULKPH-1", "", "", "", "9000"])            # invalid: missing serial_no
    serials.append(["NOSUCHSKU", "", "IMEI-BAD-1", "", "9000"])  # invalid: unknown sku
    buf = BytesIO()
    wb.save(buf)

    upload = ic.post(
        "/api/v1/imports/",
        {
            "kind": "PRODUCTS",
            "file": SimpleUploadedFile(
                "bulk_serials.xlsx", buf.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
        format="multipart",
    )
    assert upload.status_code == 201, upload.data
    assert upload.data["valid_rows"] == 1, upload.data
    assert upload.data["error_rows"] == 2, upload.data

    commit = ic.post(f"/api/v1/imports/{upload.data['id']}/commit/")
    assert commit.status_code == 400, commit.data

    # All-or-nothing: the ONE valid serial row was never posted, and the
    # product it belonged to was never created either.
    assert not SerialNumber.objects.filter(company=ns.company, serial_number="IMEI-OK-1").exists()
    assert not Product.objects.filter(company=ns.company, sku="BULKPH-1").exists()

    assert_all_invariants(ns.company)
