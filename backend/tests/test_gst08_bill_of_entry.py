"""GST-08: Bill of Entry (import ITC) — lifecycle, GL, GSTR-3B 4(A)(5)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from purchases.models import BillOfEntry
from reporting.gst_returns import build_gstr3b

pytestmark = pytest.mark.django_db

PERIOD = "2026-06"


def _enable_books(tenant):
    tenant.company.accounting_enabled = True
    tenant.company.gstin = "29ABCDE1234F1ZW"
    tenant.company.state = "Karnataka"
    tenant.company.save(update_fields=["accounting_enabled", "gstin", "state"])
    seed_chart_of_accounts(tenant.company, tenant.owner)


def test_boe_complete_posts_gl_and_flows_into_gstr3b(tenant_a):
    _enable_books(tenant_a)
    resp = tenant_a.client.post(
        "/api/v1/purchases/bills-of-entry/",
        {
            "boe_number": "BOE-0001",
            "boe_date": f"{PERIOD}-10",
            "port_code": "INMAA1",
            "assessable_value": "100000.00",
            "bcd_amount": "10000.00",
            "igst_amount": "19800.00",
            "cess_amount": "0.00",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    boe_id = resp.data["id"]
    assert resp.data["claimable_itc"] == "19800.00"

    done = tenant_a.client.post(f"/api/v1/purchases/bills-of-entry/{boe_id}/complete/")
    assert done.status_code == 200, done.data
    assert done.data["status"] == "COMPLETED"

    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="BILL_OF_ENTRY", source_id=boe_id, purpose="COMPLETE",
    )
    lines = {ln.account.code: (ln.debit or Decimal("0")) - (ln.credit or Decimal("0"))
             for ln in entry.lines.all()}
    assert lines["1330"] == Decimal("19800.00")   # Input IGST (import) — ITC
    assert lines["5110"] == Decimal("10000.00")   # BCD is a cost
    assert lines["2100"] == Decimal("-29800.00")  # AP / customs payable

    b3 = build_gstr3b(tenant_a.company, PERIOD)
    imp = b3["itc"]["import_itc"]
    assert imp["igst"] == "19800.00"
    assert imp["count"] == 1
    assert b3["itc"]["available_from_purchases"]["import_igst"] == "19800.00"


def test_boe_ineligible_itc_is_all_cost(tenant_a):
    _enable_books(tenant_a)
    boe = BillOfEntry.objects.create(
        company=tenant_a.company,
        boe_number="BOE-NIL",
        boe_date=f"{PERIOD}-11",
        igst_amount=Decimal("5000.00"),
        bcd_amount=Decimal("1000.00"),
        itc_eligibility=BillOfEntry.ItcEligibility.INELIGIBLE,
    )
    tenant_a.client.post(f"/api/v1/purchases/bills-of-entry/{boe.id}/complete/")
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="BILL_OF_ENTRY", source_id=boe.id, purpose="COMPLETE",
    )
    lines = {ln.account.code: (ln.debit or Decimal("0")) - (ln.credit or Decimal("0"))
             for ln in entry.lines.all()}
    assert "1330" not in lines
    assert lines["5110"] == Decimal("6000.00")  # igst + bcd both capitalised
    b3 = build_gstr3b(tenant_a.company, PERIOD)
    assert b3["itc"]["import_itc"]["igst"] == "0.00"


def test_boe_cancel_reverses_gl(tenant_a):
    _enable_books(tenant_a)
    boe = BillOfEntry.objects.create(
        company=tenant_a.company, boe_number="BOE-CXL", boe_date=f"{PERIOD}-12",
        igst_amount=Decimal("2000.00"),
    )
    tenant_a.client.post(f"/api/v1/purchases/bills-of-entry/{boe.id}/complete/")
    tenant_a.client.post(f"/api/v1/purchases/bills-of-entry/{boe.id}/cancel/")
    boe.refresh_from_db()
    assert boe.status == BillOfEntry.Status.CANCELLED
    assert JournalEntry.objects.filter(
        company=tenant_a.company, source_type="JOURNAL_REVERSAL",
    ).exists()
    b3 = build_gstr3b(tenant_a.company, PERIOD)
    assert b3["itc"]["import_itc"]["igst"] == "0.00"
