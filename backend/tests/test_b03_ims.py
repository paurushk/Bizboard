from datetime import date
from decimal import Decimal

import pytest
from django.db.models import Sum
from django.utils import timezone

from accounting.models import JournalEntry, JournalLine
from accounting.services import seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from purchases.models import PurchaseInvoice
from reporting.gst_periods import soft_close_period
from reporting.ims import (
    IMS_BULK_CHUNK,
    apply_ims_action,
    bulk_accept_exact,
    classify_and_match,
    credit_at_risk,
    section_16_4_deadline,
)
from reporting.ims_offline import export_offline, import_offline
from reporting.models import Gstr2bIngest, ImsActionHistory
from tests.conftest import create_draft_purchase, make_product, make_supplier


PERIOD = timezone.localdate().strftime("%Y-%m")


def _enable_books(tenant):
    tenant.company.accounting_enabled = True
    tenant.company.gstin = "29ABCDE1234F1ZW"
    tenant.company.state = "Karnataka"
    tenant.company.save(update_fields=["accounting_enabled", "gstin", "state"])
    seed_chart_of_accounts(tenant.company, tenant.owner)


def _row(company, **kwargs):
    defaults = dict(
        period=PERIOD,
        supplier_gstin="29AAAAA0000A1Z5",
        invoice_number="S-1",
        invoice_date=timezone.localdate(),
        taxable_value=Decimal("1000"),
        cgst=Decimal("90"),
        sgst=Decimal("90"),
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
    )
    defaults.update(kwargs)
    return Gstr2bIngest.objects.create(company=company, **defaults)


def _net_code(company, invoice_id, code):
    agg = JournalLine.objects.filter(
        entry__company=company,
        entry__source_type="PURCHASE_INVOICE",
        entry__source_id=invoice_id,
        entry__status="POSTED",
        account__code=code,
    ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
    return (agg["debit"] or Decimal("0")) - (agg["credit"] or Decimal("0"))


@pytest.mark.django_db
def test_ims_offline_round_trip(tenant_a):
    payload = {
        "version": "ims-offline@1.0",
        "period": PERIOD,
        "rows": [
            {
                "supplier_gstin": "29AAAAA0000A1Z5",
                "invoice_number": "OFF-1",
                "invoice_date": timezone.localdate().isoformat(),
                "taxable_value": "100.00",
                "igst": "0.00",
                "cgst": "9.00",
                "sgst": "9.00",
                "cess": "0.00",
                "ims_action": "NO_ACTION",
                "remark": "",
            }
        ],
    }
    import_offline(tenant_a.company, payload, replace=True)
    row = Gstr2bIngest.objects.get(company=tenant_a.company, invoice_number="OFF-1")
    apply_ims_action(row, "PENDING", remark="Waiting on supplier", user=tenant_a.owner)
    exported = export_offline(tenant_a.company, PERIOD)
    import_offline(tenant_a.company, exported, replace=True)
    again = export_offline(tenant_a.company, PERIOD)
    assert again["rows"] == exported["rows"]


@pytest.mark.django_db
def test_no_action_at_period_lock_is_deemed_accept(tenant_a):
    row = _row(
        tenant_a.company,
        invoice_number="DEEM-1",
        match_class=Gstr2bIngest.MatchClass.EXACT,
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
    )
    assert row.ims_action == Gstr2bIngest.ImsAction.NO_ACTION
    soft_close_period(tenant_a.company, PERIOD, tenant_a.owner)
    row.refresh_from_db()
    assert row.ims_action == Gstr2bIngest.ImsAction.ACCEPT
    assert "Deemed accept" in row.ims_remark
    hist = ImsActionHistory.objects.filter(ingest=row, action="ACCEPT")
    assert hist.exists()
    assert hist.get().payload.get("deemed") is True


@pytest.mark.django_db
def test_missing_in_books_not_deemed_accept_on_period_lock(tenant_a):
    row = _row(
        tenant_a.company,
        invoice_number="MISS-1",
        match_class=Gstr2bIngest.MatchClass.MISSING_IN_BOOKS,
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
    )
    soft_close_period(tenant_a.company, PERIOD, tenant_a.owner)
    row.refresh_from_db()
    assert row.ims_action == Gstr2bIngest.ImsAction.NO_ACTION


@pytest.mark.django_db
def test_bulk_accept_chunks_600_and_is_idempotent(tenant_a):
    rows = [
        Gstr2bIngest(
            company=tenant_a.company,
            period=PERIOD,
            supplier_gstin="29AAAAA0000A1Z5",
            invoice_number=f"BULK-{i}",
            invoice_date=timezone.localdate(),
            taxable_value=Decimal("10"),
            cgst=Decimal("0.90"),
            sgst=Decimal("0.90"),
            match_status=Gstr2bIngest.MatchStatus.MATCHED,
            match_class=Gstr2bIngest.MatchClass.EXACT,
            ims_action=Gstr2bIngest.ImsAction.NO_ACTION,
        )
        for i in range(600)
    ]
    Gstr2bIngest.objects.bulk_create(rows)
    first = bulk_accept_exact(tenant_a.company, PERIOD, user=tenant_a.owner)
    assert first["accepted"] == 600
    assert first["chunks"] == 2
    assert first["chunk_size"] == IMS_BULK_CHUNK
    second = bulk_accept_exact(tenant_a.company, PERIOD, user=tenant_a.owner)
    assert second["accepted"] == 0
    assert (
        Gstr2bIngest.objects.filter(
            company=tenant_a.company, period=PERIOD, ims_action="ACCEPT"
        ).count()
        == 600
    )


@pytest.mark.django_db
def test_section_16_4_past_window_not_pending_forever(tenant_a):
    old = date(2020, 5, 1)
    _row(tenant_a.company, invoice_number="OLD-1", invoice_date=old)
    classify_and_match(tenant_a.company, PERIOD)
    row = Gstr2bIngest.objects.get(invoice_number="OLD-1")
    assert row.section_16_4_deadline == section_16_4_deadline(old)
    assert row.section_16_4_deadline < timezone.localdate()
    assert row.match_class == Gstr2bIngest.MatchClass.POTENTIALLY_INELIGIBLE
    summary = credit_at_risk(tenant_a.company, PERIOD)
    assert Decimal(summary["itc_at_risk"]) == Decimal("0")
    assert Decimal(summary["ineligible_itc"]) > 0


@pytest.mark.django_db
def test_reject_requires_remark_and_supplier_message(tenant_a):
    row = _row(tenant_a.company, invoice_number="REJ-1")
    with pytest.raises(BusinessRuleError):
        apply_ims_action(row, "REJECT", remark="", user=tenant_a.owner)
    apply_ims_action(row, "REJECT", remark="Wrong GSTIN on invoice", user=tenant_a.owner)
    row.refresh_from_db()
    assert row.itc_eligibility == Gstr2bIngest.ItcEligibility.INELIGIBLE
    resp = tenant_a.client.post(
        f"/api/v1/reports/gstr2b/{row.id}/supplier-message/",
        {},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    body = resp.data.get("data") or resp.data
    text = body.get("text") or ""
    assert "Wrong GSTIN" in text


@pytest.mark.django_db
def test_ims_summary_api(tenant_a):
    _row(tenant_a.company, invoice_number="SUM-1")
    resp = tenant_a.client.get(f"/api/v1/reports/gstr2b/ims-summary/?period={PERIOD}")
    assert resp.status_code == 200, resp.data
    body = resp.data.get("data") or resp.data
    assert "itc_at_risk" in body or "itcAtRisk" in body


@pytest.mark.django_db
def test_gsp_pull_fail_closed_without_credentials(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/reports/gstr2b/ims-gsp-pull/",
        {"period": PERIOD},
        format="json",
    )
    assert resp.status_code == 400, resp.data


@pytest.mark.django_db
def test_exact_accept_reclasses_1390_reject_clears_1390(tenant_a):
    _enable_books(tenant_a)
    supplier = make_supplier(tenant_a.company, gstin="29DDDDD0000D1Z7")
    product = make_product(tenant_a.company, sku="B03-GL", hsn_code="1001")
    pi = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    PurchaseInvoice.objects.filter(pk=pi["id"]).update(
        invoice_date=f"{PERIOD}-04",
        itc_eligibility=PurchaseInvoice.ItcEligibility.UNREVIEWED,
    )
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{pi['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice = PurchaseInvoice.objects.get(pk=pi["id"])
    taxable = invoice.taxable_total
    grand = invoice.grand_total
    assert _net_code(tenant_a.company, invoice.id, "1390") > 0

    accept_row = _row(
        tenant_a.company,
        invoice_number=invoice.number,
        supplier_gstin="29DDDDD0000D1Z7",
        invoice_date=invoice.invoice_date,
        taxable_value=invoice.taxable_total,
        cgst=invoice.cgst_total,
        sgst=invoice.sgst_total,
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        match_class=Gstr2bIngest.MatchClass.EXACT,
        purchase_invoice=invoice,
    )
    apply_ims_action(accept_row, "ACCEPT", remark="Board accept", user=tenant_a.owner)
    invoice.refresh_from_db()
    assert invoice.taxable_total == taxable
    assert invoice.grand_total == grand
    assert invoice.itc_eligibility == PurchaseInvoice.ItcEligibility.CLAIMABLE
    assert JournalEntry.objects.filter(
        company=tenant_a.company,
        source_type="PURCHASE_INVOICE",
        source_id=invoice.id,
        purpose="ITC_RECLASS",
        status="POSTED",
    ).exists()
    assert _net_code(tenant_a.company, invoice.id, "1390") == Decimal("0")
    assert _net_code(tenant_a.company, invoice.id, "1310") + _net_code(
        tenant_a.company, invoice.id, "1320"
    ) > 0

    # Separate purchase for REJECT path (1390 still parked).
    pi2 = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "18"}],
    )
    PurchaseInvoice.objects.filter(pk=pi2["id"]).update(
        invoice_date=f"{PERIOD}-05",
        itc_eligibility=PurchaseInvoice.ItcEligibility.UNREVIEWED,
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pi2['id']}/complete/").status_code == 200
    inv2 = PurchaseInvoice.objects.get(pk=pi2["id"])
    assert _net_code(tenant_a.company, inv2.id, "1390") > 0
    reject_row = _row(
        tenant_a.company,
        invoice_number=inv2.number,
        supplier_gstin="29DDDDD0000D1Z7",
        invoice_date=inv2.invoice_date,
        taxable_value=inv2.taxable_total,
        cgst=inv2.cgst_total,
        sgst=inv2.sgst_total,
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        match_class=Gstr2bIngest.MatchClass.EXACT,
        purchase_invoice=inv2,
    )
    apply_ims_action(reject_row, "REJECT", remark="Not our invoice", user=tenant_a.owner)
    inv2.refresh_from_db()
    assert inv2.itc_eligibility == PurchaseInvoice.ItcEligibility.INELIGIBLE
    assert _net_code(tenant_a.company, inv2.id, "1390") == Decimal("0")
    assert JournalEntry.objects.filter(
        company=tenant_a.company,
        source_type="PURCHASE_INVOICE",
        source_id=inv2.id,
        purpose="ITC_REJECT",
        status="POSTED",
    ).exists()
