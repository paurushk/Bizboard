"""WP-GR1a: Tally XML masters with bill-wise outstanding; staff grant Tally per pilot (Q9)."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from core.exceptions import BusinessRuleError
from integrations.tally.adapter import parse_tally_masters_csv
from integrations.tally.xml_import import parse_tally_xml

pytestmark = pytest.mark.django_db

XML = """<?xml version="1.0" encoding="utf-16"?>
<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDATA>
<TALLYMESSAGE>
 <LEDGER NAME="Sharma Traders" ACTION="Create">
  <PARENT>Sundry Debtors</PARENT>
  <PARTYGSTIN>27AAAPL1234C1ZE</PARTYGSTIN>
  <LEDSTATENAME>Maharashtra</LEDSTATENAME>
  <OPENINGBALANCE>-15000.00</OPENINGBALANCE>
  <BILLALLOCATIONS.LIST><NAME>INV/101</NAME><BILLDATE>20260815</BILLDATE><BILLCREDITPERIOD>30 Days</BILLCREDITPERIOD><OPENINGBALANCE>-10000.00</OPENINGBALANCE></BILLALLOCATIONS.LIST>
  <BILLALLOCATIONS.LIST><NAME>INV/117</NAME><BILLDATE>20260910</BILLDATE><OPENINGBALANCE>-3000.00</OPENINGBALANCE></BILLALLOCATIONS.LIST>
 </LEDGER>
 <LEDGER NAME="Gupta Suppliers"><PARENT>Sundry Creditors</PARENT><OPENINGBALANCE>4200.00</OPENINGBALANCE>
  <BILLALLOCATIONS.LIST><NAME>GS-55</NAME><BILLDATE>20260901</BILLDATE><BILLCREDITPERIOD>15</BILLCREDITPERIOD><OPENINGBALANCE>4200.00</OPENINGBALANCE></BILLALLOCATIONS.LIST>
 </LEDGER>
 <LEDGER NAME="Cash"><PARENT>Cash-in-Hand</PARENT><OPENINGBALANCE>-500.00</OPENINGBALANCE></LEDGER>
 <STOCKITEM NAME="Steel Pipe 2in">
  <PARENT>Pipes</PARENT><BASEUNITS>Nos</BASEUNITS>
  <OPENINGBALANCE> 40 Nos</OPENINGBALANCE><OPENINGVALUE>-8000.00</OPENINGVALUE>
  <GSTDETAILS.LIST><HSNCODE>7306</HSNCODE><STATEWISEDETAILS.LIST><RATEDETAILS.LIST><GSTRATEDUTYHEAD>Integrated Tax</GSTRATEDUTYHEAD><GSTRATE>18</GSTRATE></RATEDETAILS.LIST></STATEWISEDETAILS.LIST></GSTDETAILS.LIST>
 </STOCKITEM>
</TALLYMESSAGE>
</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"""


def _bytes():
    return XML.encode("utf-16")  # Tally's usual encoding, with BOM


def test_reads_parties_bills_and_stock_from_utf16_xml():
    rows, bills = parse_tally_xml(_bytes())
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"Sharma Traders", "Gupta Suppliers", "Steel Pipe 2in"}  # Cash is skipped
    assert by_name["Sharma Traders"]["entity_type"] == "customer"
    assert by_name["Sharma Traders"]["opening_outstanding"] == "15000.00"
    assert by_name["Gupta Suppliers"]["opening_outstanding"] == "4200.00"
    pipe = by_name["Steel Pipe 2in"]
    assert pipe["opening_qty"] == "40" and pipe["purchase_price"] == "200.00"
    assert pipe["hsn_code"] == "7306" and pipe["gst_rate"] == "18"
    inv101 = next(b for b in bills if b["ref"] == "INV/101")
    assert inv101["amount"] == "10000.00" and inv101["due_date"] == "2026-09-14"


def test_preview_from_xml_counts_bills():
    preview = parse_tally_masters_csv(_bytes(), "masters.xml")
    assert preview["source_format"] == "tally_xml"
    assert preview["counts"] == {**preview["counts"], "customers": 1, "suppliers": 1, "products": 1, "bills": 3}


def test_doctype_and_entities_are_refused():
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><ENVELOPE>&a;</ENVELOPE>'
    with pytest.raises(BusinessRuleError, match="DOCTYPE"):
        parse_tally_xml(evil)
    with pytest.raises(BusinessRuleError):
        parse_tally_xml(b"<ENVELOPE><LEDGER></ENVELOPE>")


def test_import_makes_one_opening_document_per_bill_and_ties_to_the_party_total(tenant_a):
    from masters.models import Customer, Supplier
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    up = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("masters.xml", _bytes(), content_type="application/xml")},
        format="multipart",
    )
    assert up.status_code == 201, up.content
    body = up.data.get("data", up.data)
    run_id = body.get("sync_run_id") or body.get("syncRunId")
    commit = tenant_a.client.post("/api/v1/integrations/tally/commit/", {"sync_run_id": run_id}, format="json")
    assert commit.status_code == 200, commit.content

    cust = Customer.objects.get(company=tenant_a.company, name="Sharma Traders")
    docs = SalesInvoice.objects.filter(company=tenant_a.company, customer=cust, is_opening_balance=True)
    assert docs.count() == 3  # two bills + 2,000 on account
    assert sum((d.grand_total for d in docs), Decimal("0")) == Decimal("15000.00")
    assert {str(d.due_date) for d in docs if d.due_date} == {"2026-09-14", "2026-09-10"}
    sup = Supplier.objects.get(company=tenant_a.company, name="Gupta Suppliers")
    bill = PurchaseInvoice.objects.get(company=tenant_a.company, supplier=sup, is_opening_balance=True)
    assert bill.grand_total == Decimal("4200.00") and str(bill.due_date) == "2026-09-16"
    recon = commit.data["result"]["reconciliation"]
    assert recon["receivables"]["pass"] and recon["payables"]["pass"], recon


@override_settings(ENABLE_TALLY=False)
def test_tally_is_off_until_staff_grant_it_and_the_grant_is_audited(tenant_a, django_user_model):
    from accounts.rollout_grants import grantable_keys, set_flag
    from core.models import AuditEvent

    blocked = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("m.xml", _bytes(), content_type="application/xml")}, format="multipart",
    )
    assert blocked.status_code in (403, 404)  # the gate hides the feature

    assert "ENABLE_TALLY" in grantable_keys() and "ENABLE_MANUFACTURING" not in grantable_keys()
    staff = django_user_model.objects.create_superuser(email="ops@bizboard.test", password="Ops-Pass-123")
    with pytest.raises(BusinessRuleError):
        set_flag(tenant_a.company, key="ENABLE_MANUFACTURING", on=True, staff_user=staff, reason="nope nope")
    set_flag(tenant_a.company, key="ENABLE_TALLY", on=True, staff_user=staff, reason="Pilot moving from Tally",
             ticket="T-12")
    assert AuditEvent.objects.filter(company=tenant_a.company, action="rollout_flag.granted").exists()
    allowed = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("m.xml", _bytes(), content_type="application/xml")}, format="multipart",
    )
    assert allowed.status_code == 201, allowed.content
    set_flag(tenant_a.company, key="ENABLE_TALLY", on=False, staff_user=staff, reason="Cutover finished")
    again = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("m.xml", _bytes(), content_type="application/xml")}, format="multipart",
    )
    assert again.status_code in (403, 404)
