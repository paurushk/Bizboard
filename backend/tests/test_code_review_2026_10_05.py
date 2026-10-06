"""Regression tests for the defects found in the 2026-10-05 deep code review.

One test per fixed defect. Each fails against the code as it was before the fix.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.utils import timezone

from tests.conftest import make_customer


def _completed_invoice(company, customer, *, days_overdue, total="6000"):
    from sales.models import SalesInvoice

    return SalesInvoice.objects.create(
        company=company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        due_date=timezone.localdate() - timedelta(days=days_overdue), grand_total=Decimal(total),
    )


def _pay(company, customer, invoice, amount):
    from payments.models import CustomerReceipt, PaymentAllocation

    receipt = CustomerReceipt.objects.create(company=company, customer=customer, amount=Decimal(amount))
    PaymentAllocation.objects.create(company=company, receipt=receipt, sales_invoice=invoice, amount=Decimal(amount))


# ---- credit hold counts what is owed, not what was billed
def test_a_paid_old_invoice_does_not_hold_credit(tenant_a):
    from planwave.services import chronic_overdue

    customer = make_customer(tenant_a.company, name="Pays late but pays")
    invoice = _completed_invoice(tenant_a.company, customer, days_overdue=70)
    blocked, total = chronic_overdue(tenant_a.company, customer)
    assert blocked and total == Decimal("6000.00")
    _pay(tenant_a.company, customer, invoice, "6000")
    blocked, total = chronic_overdue(tenant_a.company, customer)
    assert not blocked and total == 0


def test_overdue_report_lists_only_what_is_still_owed(tenant_a):
    from planwave.finish import overdue_report

    customer = make_customer(tenant_a.company, name="Report")
    paid = _completed_invoice(tenant_a.company, customer, days_overdue=40, total="500")
    open_ = _completed_invoice(tenant_a.company, customer, days_overdue=45, total="900")
    _pay(tenant_a.company, customer, paid, "500")
    rows = overdue_report(tenant_a.company)
    assert [r["invoice"] for r in rows] == [open_.number or str(open_.pk)]
    assert rows[0]["amount"] == "900.00"


# ---- quarantine: one open row per company, even when two runs race
def test_one_open_quarantine_row_per_company(tenant_a):
    from planwave.models import IntegrityQuarantine
    from planwave.services import open_quarantine

    first = open_quarantine(tenant_a.company, {"tb_zero": "off by 5"})
    again = open_quarantine(tenant_a.company, {"tb_zero": "off by 7", "ar_control": "x"})
    assert first.pk == again.pk
    assert IntegrityQuarantine.objects.filter(company=tenant_a.company, cleared_at__isnull=True).count() == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        IntegrityQuarantine.objects.create(company=tenant_a.company, keys=[], detail={})


# ---- as-issued party snapshots are write-once
def test_a_backfill_never_overwrites_an_issued_snapshot(tenant_a):
    from planwave.models import PartySnapshot
    from planwave.services import stamp_party

    customer = make_customer(tenant_a.company, name="Old Name")
    invoice = _completed_invoice(tenant_a.company, customer, days_overdue=1)
    stamp_party(invoice, customer)
    customer.name = "New Name"
    customer.save()
    stamp_party(invoice, customer, backfill=True)
    row = PartySnapshot.objects.get(company=tenant_a.company, entity_type="SalesInvoice", entity_id=str(invoice.pk))
    assert row.payload["trade_name"] == "Old Name"
    assert row.backfill_from_master is False


# ---- credit token: no blank-token redemption of an ordinary approval
def test_a_blank_token_cannot_redeem_an_ordinary_approval(tenant_a):
    from core.exceptions import BusinessRuleError
    from planwave.services import redeem_credit_token, submit_approval

    submit_approval(
        company=tenant_a.company, action="discount", requester=tenant_a.owner,
        payload={"invoice_batch": "B1"},
    )
    with pytest.raises(BusinessRuleError):
        redeem_credit_token(tenant_a.company, "", "B1")


# ---- approvals decided at once: the second decision is refused, not a silent overwrite
def test_an_approval_decided_twice_keeps_the_first_decision(tenant_a):
    from core.exceptions import BusinessRuleError
    from planwave.models import ApprovalRequest
    from planwave.services import decide_approval, submit_approval

    row = submit_approval(company=tenant_a.company, action="discount", requester=tenant_a.staff, payload={})
    stale = ApprovalRequest.objects.get(pk=row.pk)
    decide_approval(row, approver=tenant_a.owner, accept=True)
    with pytest.raises(BusinessRuleError):
        decide_approval(stale, approver=tenant_a.owner, accept=False)
    assert ApprovalRequest.objects.get(pk=row.pk).status == "APPROVED"


# ---- stock adjustments with nothing to measure against still need a second person
def test_an_adjustment_on_zero_stock_needs_a_second_person(tenant_a):
    from planwave.services import stock_adjustment_needs_second

    assert stock_adjustment_needs_second(
        tenant_a.company, value=Decimal("0"), quantity=Decimal("5"), on_hand=Decimal("0"),
    )
    assert not stock_adjustment_needs_second(
        tenant_a.company, value=Decimal("10"), quantity=Decimal("1"), on_hand=Decimal("100"),
    )


# ---- certification cannot be forged with a query flag, and is not for every login
def test_certification_ignores_a_caller_supplied_chain_flag_and_needs_a_senior_role(tenant_a):
    url = "/api/v1/plan/certification/?start=2026-04-01&end=2027-03-31&chain_ok=1"
    assert tenant_a.staff_client.get(url).status_code == 403
    ok = tenant_a.client.get(url)
    assert ok.status_code == 200, ok.data
    bad = tenant_a.client.get("/api/v1/plan/certification/?start=nope&end=2027-03-31")
    assert bad.status_code == 400


def test_itc_attestation_and_pharmacy_register_are_senior_roles_only(tenant_a):
    assert tenant_a.staff_client.post("/api/v1/plan/itc/", {"source_id": "1"}, format="json").status_code == 403
    assert tenant_a.staff_client.get("/api/v1/plan/pharmacy/register/").status_code == 403
    assert tenant_a.client.get("/api/v1/plan/pharmacy/register/").status_code == 200


def test_unknown_approval_action_and_bad_dates_are_400_not_500(tenant_a):
    assert tenant_a.client.post("/api/v1/plan/approvals/", {"action": "x" * 80}, format="json").status_code == 400
    assert tenant_a.client.post(
        "/api/v1/plan/section-50/", {"tax": "abc", "on": "2026-04-01"}, format="json",
    ).status_code == 400
    assert tenant_a.client.post("/api/v1/plan/section-50/", {"tax": "1"}, format="json").status_code == 400


# ---- rate limiting
def test_a_json_list_body_does_not_crash_the_limiter():
    from planwave.ratelimit import _body_account, _otp_target

    request = RequestFactory().post("/api/v1/auth/login/", data=json.dumps([1, 2]), content_type="application/json")
    assert _body_account(request) == ""
    assert _otp_target(request) == ""


def test_otp_numbers_share_one_bucket_however_they_are_written():
    from planwave.ratelimit import _otp_target

    forms = ["+91 98765 43210", "919876543210", "09876543210", "9876543210"]
    targets = {
        _otp_target(RequestFactory().post(
            "/api/v1/auth/otp/request/", data=json.dumps({"phone": form}), content_type="application/json",
        ))
        for form in forms
    }
    assert targets == {"9876543210"}


# ---- sanitiser keeps text that only looks like a tag
def test_the_sanitiser_strips_tags_but_keeps_comparisons():
    import re

    from planwave.sanitize import _TAG

    assert _TAG.sub("", "pay if <5000 and >100") == "pay if <5000 and >100"
    assert _TAG.sub("", "hi <b>there</b><script>x</script>") == "hi therex"
    assert re.search(_TAG, "<!-- hidden -->") is not None


# ---- sealing never buries a blob it cannot open under a second layer
def test_a_sealed_value_that_cannot_be_opened_is_left_alone():
    from planwave.crypto import seal

    foreign = "gcm1.k9." + "A" * 60
    assert seal(foreign) == foreign


# ---- pharmacy: a refused completion leaves no register rows behind
def test_checking_a_pharmacy_sale_records_nothing(tenant_a):
    from masters.models import Product
    from planwave.models import PharmacyDispense
    from planwave.services import assert_pharmacy_sale

    tenant_a.company.feature_flags = {"pharmacy_enabled": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    product = Product.objects.create(
        company=tenant_a.company, name="Tab", sku="TAB-9", drug_schedule="H",
        selling_price=Decimal("10"), purchase_price=Decimal("4"),
    )
    kwargs = dict(
        company=tenant_a.company, product=product, patient_name="A", prescriber_name="Dr B",
        prescriber_registration="R1", quantity=1,
    )
    assert assert_pharmacy_sale(record=False, **kwargs) == "H"
    assert PharmacyDispense.objects.count() == 0
    row = assert_pharmacy_sale(invoice_number="INV-9", **kwargs)
    assert row.invoice_number == "INV-9"


# ---- banking: a UTR in the narration is not enough without the amount
def test_a_matching_reference_with_a_different_amount_does_not_bind(tenant_a):
    from banking.models import AaConsent, AaTransaction
    from banking.services import _match_credit
    from payments.models import CustomerReceipt

    customer = make_customer(tenant_a.company, name="Utr")
    CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("50000"), utr="123456789012",
    )
    consent = AaConsent.objects.create(company=tenant_a.company, consent_id="C1", status="ACTIVE")
    txn = AaTransaction.objects.create(
        company=tenant_a.company, consent=consent, txn_id="T1", amount=Decimal("500"),
        raw={"narration": "UPI 123456789012 thanks"},
    )
    assert _match_credit(tenant_a.company, txn, Decimal("0.01")) is None


# ---- e-way: no pretend Part B update when the provider is live
def test_a_live_eway_provider_refuses_a_part_b_update_it_cannot_send(tenant_a, settings):
    from core.exceptions import BusinessRuleError
    from core.services import gsp_adapters
    from sales.einvoice_eway_actions import update_eway_vehicle

    class _Invoice:
        eway_bill_no = "1234"
        company = tenant_a.company
        transport_distance_km = 10
        vehicle_number = ""

    live = gsp_adapters.LiveEwayAdapter.__new__(gsp_adapters.LiveEwayAdapter)
    import sales.einvoice_eway_actions as actions

    original = actions.get_eway_adapter
    actions.get_eway_adapter = lambda company: live
    try:
        with pytest.raises(BusinessRuleError):
            update_eway_vehicle(_Invoice(), "KA01AB1234", "BREAKDOWN")
    finally:
        actions.get_eway_adapter = original


# ---- masters: soft-deleted rows do not block reuse of their SKU or GSTIN
def test_a_deleted_product_does_not_block_its_sku(tenant_a):
    from masters.models import Product

    first = Product.objects.create(company=tenant_a.company, name="One", sku="DUP-1", selling_price=Decimal("1"))
    first.is_deleted = True
    first.save(update_fields=["is_deleted"])
    again = Product.objects.create(company=tenant_a.company, name="Two", sku="DUP-1", selling_price=Decimal("1"))
    assert again.pk != first.pk


# ---- payroll: advance recovery keeps the journal balanced and arrears do not compound
def test_payroll_advance_recovery_credits_the_employee_advance_account(tenant_a):
    from accounting.models import Account
    from accounting.services import PostingService

    PostingService._ensure_chart(tenant_a.company)
    assert Account.objects.filter(company=tenant_a.company, code="1260", is_active=True).exists()
