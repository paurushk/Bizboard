"""CREDIT_NOTES_IMPLEMENTATION_PLAN.md: credit / debit note register, permissions, accounting and cross-module rules.

Item ids (CN-xx, DN-xx, DEP-xx, NEW-xx) refer to that plan.
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from core.models import AuditEvent
from sales.models import SalesCreditNote
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    make_customer,
    make_product,
    make_tenant,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------- helpers


def _client_for(tenant, role, *, email, **caps):
    user = User.objects.create_user(email=email, password="StrongPass123!", full_name=email)
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, **caps)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _completed_invoice(tenant, customer, product, qty="5", price="100", stock=True):
    if stock:
        add_stock(tenant, product, "50")
    inv = create_draft_invoice(
        tenant, customer, [{"product": product.id, "quantity": qty, "unit_price": price}],
    )
    done = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    return inv


def _draft_note(client, kind, customer, invoice, product, qty="1", price="100", reason="CORRECTION_OF_INVOICE", **extra):
    resp = client.post(
        f"/api/v1/sales/{kind}-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice["id"],
            "reason": reason,
            "items": [{"product": product.id, "quantity": qty, "unit_price": price}],
            **extra,
        },
        format="json",
    )
    return resp


def _complete(client, kind, note_id, **body):
    return client.post(f"/api/v1/sales/{kind}-notes/{note_id}/complete/", body, format="json")


@pytest.fixture
def world(tenant_a):
    product = make_product(tenant_a.company, sku="CN-P1")
    customer = make_customer(tenant_a.company, name="Note Customer")
    invoice = _completed_invoice(tenant_a, customer, product)
    return tenant_a, customer, product, invoice


# ---------------------------------------------------------------- CN-03 / DN-03 permissions


def test_accountant_can_create_and_complete_credit_and_debit_notes(world):
    tenant, customer, product, invoice = world
    accountant = _client_for(tenant, CompanyUser.Role.ACCOUNTANT, email="acct@alpha.test")
    cn = _draft_note(accountant, "credit", customer, invoice, product, price="10")
    assert cn.status_code == 201, cn.data
    assert _complete(accountant, "credit", cn.data["id"], confirm_price_override=True).status_code == 200
    dn = _draft_note(accountant, "debit", customer, invoice, product, price="10")
    assert dn.status_code == 201, dn.data
    assert _complete(accountant, "debit", dn.data["id"], confirm_additional_debit=True).status_code == 200


def test_viewer_and_unflagged_staff_cannot_complete_notes(world):
    tenant, customer, product, invoice = world
    viewer = _client_for(tenant, CompanyUser.Role.VIEWER, email="viewer@alpha.test")
    assert _draft_note(viewer, "credit", customer, invoice, product).status_code == 403
    assert _draft_note(viewer, "debit", customer, invoice, product).status_code == 403
    # Sales staff without can_create_sales is refused too.
    staff = tenant.staff_client
    assert _draft_note(staff, "credit", customer, invoice, product).status_code == 403


def test_accountant_cannot_delete_a_draft_note(world):
    tenant, customer, product, invoice = world
    cn = _draft_note(tenant.client, "credit", customer, invoice, product, price="10")
    accountant = _client_for(tenant, CompanyUser.Role.ACCOUNTANT, email="acct2@alpha.test")
    assert accountant.delete(f"/api/v1/sales/credit-notes/{cn.data['id']}/").status_code == 403


def test_non_owner_completion_is_audited(world):
    tenant, customer, product, invoice = world
    accountant = _client_for(tenant, CompanyUser.Role.ACCOUNTANT, email="acct3@alpha.test")
    cn = _draft_note(accountant, "credit", customer, invoice, product, price="10")
    assert _complete(accountant, "credit", cn.data["id"], confirm_price_override=True).status_code == 200
    assert AuditEvent.objects.filter(
        company=tenant.company, action="note_completed_by_non_owner", entity_id=str(cn.data["id"]),
    ).exists()


# ---------------------------------------------------------------- CN-02 / DN-02 filters, CN-11 / DN-10 export


def test_register_filters_search_status_dates_and_invoice(world):
    tenant, customer, product, invoice = world
    other_customer = make_customer(tenant.company, name="Someone Else")
    other_invoice = _completed_invoice(tenant, other_customer, make_product(tenant.company, sku="CN-P2"))
    a = _draft_note(tenant.client, "debit", customer, invoice, product, price="10").data
    b = _draft_note(tenant.client, "debit", other_customer, other_invoice, product, price="10",).data \
        if False else None
    assert _complete(tenant.client, "debit", a["id"], confirm_additional_debit=True).status_code == 200

    def ids(**params):
        resp = tenant.client.get("/api/v1/sales/debit-notes/", params)
        assert resp.status_code == 200, resp.data
        rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        return {row["id"] for row in rows}

    assert ids() == {a["id"]}
    assert ids(search="Note Customer") == {a["id"]}
    assert ids(search="nobody-matches-this") == set()
    from sales.models import SalesInvoice

    assert ids(search=SalesInvoice.objects.get(pk=invoice["id"]).number) == {a["id"]}
    assert ids(status="COMPLETED") == {a["id"]}
    assert ids(status="DRAFT") == set()
    assert ids(invoice=invoice["id"]) == {a["id"]}
    assert ids(invoice=other_invoice["id"]) == set()
    assert ids(date_from="2000-01-01", date_to="2999-01-01") == {a["id"]}
    assert ids(date_from="2999-01-01") == set()


def test_register_filter_rejects_bad_or_inverted_dates(tenant_a):
    for kind in ("credit", "debit"):
        bad = tenant_a.client.get(f"/api/v1/sales/{kind}-notes/", {"date_from": "not-a-date"})
        assert bad.status_code == 400
        inverted = tenant_a.client.get(
            f"/api/v1/sales/{kind}-notes/", {"date_from": "2026-05-01", "date_to": "2026-04-01"}
        )
        assert inverted.status_code == 400


def test_register_never_returns_another_companys_notes(world):
    tenant, customer, product, invoice = world
    mine = _draft_note(tenant.client, "credit", customer, invoice, product, price="10").data
    other = make_tenant("gamma", state="Karnataka")
    resp = other.client.get("/api/v1/sales/credit-notes/", {"search": "Note Customer"})
    assert resp.status_code == 200
    rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    assert mine["id"] not in {row["id"] for row in rows}


def test_export_csv_honours_filters_and_neutralises_formulas(tenant_a):
    product = make_product(tenant_a.company, sku="CN-EXP")
    customer = make_customer(tenant_a.company, name="=HYPERLINK(1)")
    invoice = _completed_invoice(tenant_a, customer, product)
    note = _draft_note(tenant_a.client, "credit", customer, invoice, product, price="10").data
    resp = tenant_a.client.get("/api/v1/sales/credit-notes/export/", {"status": "DRAFT"})
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    text = resp.content.decode()
    assert "'=HYPERLINK(1)" in text and ",=HYPERLINK" not in text
    assert note["id"]
    empty = tenant_a.client.get("/api/v1/sales/credit-notes/export/", {"status": "COMPLETED"})
    assert len(empty.content.decode().strip().splitlines()) == 1  # header only


def test_export_requires_export_permission(world):
    tenant, *_ = world
    plain = _client_for(tenant, CompanyUser.Role.SALES_STAFF, email="plain@alpha.test", can_create_sales=True)
    assert plain.get("/api/v1/sales/credit-notes/export/").status_code == 403
    assert plain.get("/api/v1/sales/debit-notes/export/").status_code == 403


# ---------------------------------------------------------------- DN-07 excess debit


def _excess_debit(client, customer, invoice, product, price):
    dn = _draft_note(client, "debit", customer, invoice, product, qty="1", price=price)
    assert dn.status_code == 201, dn.data
    return dn.data["id"]


def test_debit_above_invoice_value_is_refused_without_owner_override(world):
    tenant, customer, product, invoice = world  # invoice total is 5 x 100 + GST = 590
    dn_id = _excess_debit(tenant.client, customer, invoice, product, "1000")
    refused = _complete(tenant.client, "debit", dn_id, confirm_additional_debit=True)
    assert refused.status_code == 400
    assert "exceeds original invoice value" in str(refused.data)


def test_owner_can_override_with_reason_and_it_is_audited(world):
    tenant, customer, product, invoice = world
    dn_id = _excess_debit(tenant.client, customer, invoice, product, "1000")
    no_reason = _complete(
        tenant.client, "debit", dn_id, confirm_additional_debit=True, confirm_excessive_debit=True
    )
    assert no_reason.status_code == 400 and "reason" in str(no_reason.data).lower()
    ok = _complete(
        tenant.client, "debit", dn_id, confirm_additional_debit=True,
        confirm_excessive_debit=True, excessive_debit_reason="Supplier price revision",
    )
    assert ok.status_code == 200, ok.data
    assert AuditEvent.objects.filter(
        company=tenant.company, action="debit_note_excess_override", entity_id=str(dn_id),
    ).exists()


def test_non_owner_cannot_use_the_override(world):
    tenant, customer, product, invoice = world
    accountant = _client_for(tenant, CompanyUser.Role.ACCOUNTANT, email="acct4@alpha.test")
    dn_id = _excess_debit(accountant, customer, invoice, product, "1000")
    resp = _complete(
        accountant, "debit", dn_id, confirm_additional_debit=True,
        confirm_excessive_debit=True, excessive_debit_reason="trying",
    )
    assert resp.status_code == 400 and "Owner" in str(resp.data)


def test_override_is_capped_at_three_times_the_invoice(world):
    tenant, customer, product, invoice = world
    dn_id = _excess_debit(tenant.client, customer, invoice, product, "5000")  # ~ 5900 > 3 x 590
    resp = _complete(
        tenant.client, "debit", dn_id, confirm_additional_debit=True,
        confirm_excessive_debit=True, excessive_debit_reason="Too big",
    )
    assert resp.status_code == 400 and "3x" in str(resp.data)


# ---------------------------------------------------------------- DEP-02 returns headroom


def _return_all(tenant, customer, invoice, product, qty):
    resp = tenant.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id, "sales_invoice": invoice["id"],
            "items": [{"product": product.id, "quantity": str(qty), "unit_price": "100"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return tenant.client.post(f"/api/v1/sales/returns/{resp.data['id']}/complete/", {}, format="json")


def test_rate_correction_credit_note_does_not_block_a_goods_return(world):
    tenant, customer, product, invoice = world  # 5 units at 100
    cn = _draft_note(tenant.client, "credit", customer, invoice, product, qty="5", price="10")
    assert _complete(tenant.client, "credit", cn.data["id"], confirm_price_override=True).status_code == 200
    # 5 x 10 credited as a price cut; all 5 units are still returnable (value headroom allows part).
    resp = _return_all(tenant, customer, invoice, product, 2)
    assert resp.status_code == 200, resp.data


def test_full_price_quantity_credit_still_consumes_returnable_units(world):
    tenant, customer, product, invoice = world
    cn = _draft_note(tenant.client, "credit", customer, invoice, product, qty="3", price="100")
    assert _complete(tenant.client, "credit", cn.data["id"], confirm_price_override=True).status_code == 200
    resp = _return_all(tenant, customer, invoice, product, 4)
    assert resp.status_code == 400  # only 2 units are left to return


def test_post_sale_discount_never_consumes_returnable_units(world):
    tenant, customer, product, invoice = world
    cn = _draft_note(
        tenant.client, "credit", customer, invoice, product, qty="2", price="100", reason="POST_SALE_DISCOUNT",
    )
    assert _complete(tenant.client, "credit", cn.data["id"], confirm_price_override=True).status_code == 200
    from sales.return_service import ReturnService
    from sales.models import SalesInvoice

    state = ReturnService.line_state(SalesInvoice.objects.get(pk=invoice["id"]))
    assert state["standalone"] == {} or all(v == 0 for v in state["standalone"].values())


# ---------------------------------------------------------------- DEP-04 contra revenue


def _credit_note_debits(tenant, note_id):
    from accounting.models import JournalEntry

    entry = JournalEntry.objects.get(
        company=tenant.company, source_type="SALES_CREDIT_NOTE", source_id=note_id, purpose="COMPLETE",
    )
    return {line.account.code for line in entry.lines.all() if line.debit}


def _with_accounting(tenant):
    tenant.company.accounting_enabled = True
    tenant.company.save(update_fields=["accounting_enabled"])


def test_credit_note_posts_to_sales_4100_by_default(tenant_a):
    _with_accounting(tenant_a)
    product = make_product(tenant_a.company, sku="CN-GL1")
    customer = make_customer(tenant_a.company)
    invoice = _completed_invoice(tenant_a, customer, product)
    cn = _draft_note(tenant_a.client, "credit", customer, invoice, product, price="10").data
    assert _complete(tenant_a.client, "credit", cn["id"], confirm_price_override=True).status_code == 200
    assert "4100" in _credit_note_debits(tenant_a, cn["id"])


def test_credit_note_posts_to_contra_4110_when_enabled_and_debit_note_stays_on_4100(tenant_a):
    _with_accounting(tenant_a)
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_CONTRA_SALES_ACCOUNT"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    product = make_product(tenant_a.company, sku="CN-GL2")
    customer = make_customer(tenant_a.company)
    invoice = _completed_invoice(tenant_a, customer, product)
    cn = _draft_note(tenant_a.client, "credit", customer, invoice, product, price="10").data
    assert _complete(tenant_a.client, "credit", cn["id"], confirm_price_override=True).status_code == 200
    assert "4110" in _credit_note_debits(tenant_a, cn["id"])

    from accounting.models import JournalEntry

    dn = _draft_note(tenant_a.client, "debit", customer, invoice, product, price="10").data
    assert _complete(tenant_a.client, "debit", dn["id"], confirm_additional_debit=True).status_code == 200
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_DEBIT_NOTE", source_id=dn["id"], purpose="COMPLETE",
    )
    credited = {line.account.code for line in entry.lines.all() if line.credit}
    assert "4100" in credited and "4110" not in credited


# ---------------------------------------------------------------- DEP-06 IRN submit roles


def test_note_irn_submit_is_not_owner_only_any_more(world):
    tenant, customer, product, invoice = world
    cn = _draft_note(tenant.client, "credit", customer, invoice, product, price="10").data
    assert _complete(tenant.client, "credit", cn["id"], confirm_price_override=True).status_code == 200
    accountant = _client_for(tenant, CompanyUser.Role.ACCOUNTANT, email="acct5@alpha.test")
    resp = accountant.post(f"/api/v1/sales/credit-notes/{cn['id']}/submit-einvoice/")
    # e-invoicing is off for this company: the call gets past the role check and fails on that.
    assert "Only Owner, Manager or Accountant" not in str(resp.data)
    staff = _client_for(tenant, CompanyUser.Role.SALES_STAFF, email="staff2@alpha.test", can_create_sales=True)
    refused = staff.post(f"/api/v1/sales/credit-notes/{cn['id']}/submit-einvoice/")
    assert "Only Owner, Manager or Accountant" in str(refused.data)


# ---------------------------------------------------------------- DEP-05 HSN on B2B notes


def test_b2b_credit_note_without_hsn_cannot_complete(tenant_a):
    product = make_product(tenant_a.company, sku="CN-HSN", hsn_code="")
    customer = make_customer(tenant_a.company, name="B2B Buyer", gstin="29BBBBB1111B1Z5")
    invoice = _completed_invoice(tenant_a, customer, product)
    cn = _draft_note(tenant_a.client, "credit", customer, invoice, product, price="10").data
    resp = _complete(tenant_a.client, "credit", cn["id"], confirm_price_override=True)
    assert resp.status_code == 400
    assert "HSN" in str(resp.data)


# ---------------------------------------------------------------- DEP-07 referral reward completion


def _approved_reward(tenant):
    from crm.models import ReferralReward
    from crm.pipeline import capture_lead

    from .test_growth_os import _flags
    from .test_referral_paid_status import _bill_and_complete

    _flags(tenant.company)
    referrer = make_customer(tenant.company, name="Referrer R")
    _bill_and_complete(tenant, referrer, amount="500")
    issued = tenant.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": referrer.id, "reward_type": "FLAT", "reward_value": "40"},
        format="json",
    )
    lead = capture_lead(
        tenant.company, tenant.owner, name="Referred", phone="9000000777", referral_code=issued.data["code"],
    )
    converted = tenant.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": "100"}, format="json"
    )
    reward = ReferralReward.objects.get(opportunity_id=converted.data["opportunity"]["id"])
    assert tenant.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/").status_code == 200
    return reward


def test_mark_paid_completes_the_reward_credit_note(tenant_a):
    from crm.models import ReferralReward

    reward = _approved_reward(tenant_a)
    paid = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert paid.status_code == 200, paid.data
    reward.refresh_from_db()
    assert reward.reward_status == ReferralReward.Status.PAID
    assert reward.credit_note.status == SalesCreditNote.Status.COMPLETED


def test_reward_stays_approved_when_its_credit_note_cannot_complete(tenant_a):
    from crm.models import ReferralReward
    from reporting.gst_periods import soft_close_period

    reward = _approved_reward(tenant_a)
    today = date.today()
    soft_close_period(tenant_a.company, f"{today.year:04d}-{today.month:02d}", tenant_a.owner)
    resp = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert resp.status_code == 400
    reward.refresh_from_db()
    assert reward.reward_status == ReferralReward.Status.APPROVED
    assert reward.credit_note_id is None  # the whole step rolled back


# ---------------------------------------------------------------- DEP-09 search


def test_universal_search_finds_credit_and_debit_notes(world):
    tenant, customer, product, invoice = world
    cn = _draft_note(tenant.client, "credit", customer, invoice, product, price="10").data
    dn = _draft_note(tenant.client, "debit", customer, invoice, product, price="10").data
    resp = tenant.client.get("/api/v1/search/", {"q": "Note Customer"})
    assert resp.status_code == 200
    assert cn["id"] in {row["id"] for row in resp.data["credit_notes"]}
    assert dn["id"] in {row["id"] for row in resp.data["debit_notes"]}
    viewer = _client_for(tenant, CompanyUser.Role.VIEWER, email="viewer2@alpha.test")
    hidden = viewer.get("/api/v1/search/", {"q": "Note Customer"})
    assert hidden.data["credit_notes"] == [] and hidden.data["debit_notes"] == []


# ---------------------------------------------------------------- NEW-01 period lock


def test_note_in_a_closed_gst_period_is_refused(world):
    tenant, customer, product, invoice = world
    from reporting.gst_periods import soft_close_period

    cn = _draft_note(tenant.client, "credit", customer, invoice, product, price="10").data
    today = date.today()
    soft_close_period(tenant.company, f"{today.year:04d}-{today.month:02d}", tenant.owner)
    resp = _complete(tenant.client, "credit", cn["id"], confirm_price_override=True)
    assert resp.status_code == 400 and "SOFT_CLOSED" in str(resp.data)


# ---------------------------------------------------------------- NEW-08 repair command


def test_repair_command_reports_then_fixes_orphan_return_reason_drafts(world):
    from django.core.management import call_command

    tenant, customer, product, invoice = world
    cn = _draft_note(tenant.client, "credit", customer, invoice, product, price="10").data
    SalesCreditNote.objects.filter(pk=cn["id"]).update(reason="SALES_RETURN")
    call_command("repair_note_data")
    assert SalesCreditNote.objects.get(pk=cn["id"]).reason == "SALES_RETURN"  # dry run
    call_command("repair_note_data", apply=True)
    assert SalesCreditNote.objects.get(pk=cn["id"]).reason == "CORRECTION_OF_INVOICE"


# ---------------------------------------------------------------- purchase twins (DEP-12)


def test_purchase_note_registers_support_filters_and_export(tenant_a):
    from tests.conftest import make_supplier

    make_supplier(tenant_a.company)
    for kind in ("credit", "debit"):
        listed = tenant_a.client.get(f"/api/v1/purchases/{kind}-notes/", {"search": "x", "status": "DRAFT"})
        assert listed.status_code == 200, listed.data
        bad = tenant_a.client.get(f"/api/v1/purchases/{kind}-notes/", {"date_from": "garbage"})
        assert bad.status_code == 400
        exported = tenant_a.client.get(f"/api/v1/purchases/{kind}-notes/export/")
        assert exported.status_code == 200
        assert exported.content.decode().startswith("Number,")


# ---------------------------------------------------------------- DN-07: the cap is cumulative


def test_splitting_a_big_debit_into_several_notes_cannot_sidestep_the_cap(world):
    tenant, customer, product, invoice = world  # invoice value 590
    first = _excess_debit(tenant.client, customer, invoice, product, "400")  # 472 with GST
    second = _excess_debit(tenant.client, customer, invoice, product, "400")
    assert _complete(tenant.client, "debit", first, confirm_additional_debit=True).status_code == 200
    refused = _complete(tenant.client, "debit", second, confirm_additional_debit=True)
    assert refused.status_code == 400
    assert "exceeds original invoice value" in str(refused.data)


# ---------------------------------------------------------------- NEW-06: cancel after the advance was used


def test_cancelling_a_credit_note_after_its_advance_was_used_is_audited(tenant_a):
    from sales.models import SalesInvoice
    from tests.conftest import make_default_bank

    product = make_product(tenant_a.company, sku="CN-PEEL")
    customer = make_customer(tenant_a.company, name="Peel Customer")
    first = _completed_invoice(tenant_a, customer, product)
    second = _completed_invoice(tenant_a, customer, product, stock=False)
    make_default_bank(tenant_a.company)
    total = str(SalesInvoice.objects.get(pk=first["id"]).grand_total)
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": total, "mode": "UPI"},
        format="json",
    ).data
    assert tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt["id"], "sales_invoice": first["id"], "amount": total},
        format="json",
    ).status_code == 201
    # Credit the whole (paid) invoice: the payment becomes the customer's advance.
    cn = _draft_note(tenant_a.client, "credit", customer, first, product, qty="5", price="100").data
    done = _complete(tenant_a.client, "credit", cn["id"], confirm_paid_invoice=True, confirm_price_override=True)
    assert done.status_code == 200, done.data
    # The advance is then spent on the other invoice.
    assert tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt["id"], "sales_invoice": second["id"], "amount": total},
        format="json",
    ).status_code == 201
    cancelled = tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn['id']}/cancel/")
    assert cancelled.status_code == 200, cancelled.data
    event = AuditEvent.objects.get(
        company=tenant_a.company, action="credit_note_cancel_partial_restore", entity_id=str(cn["id"]),
    )
    assert Decimal(event.metadata["shortfall"]) > 0


# ---------------------------------------------------------------- NEW-04: reverse charge notes balance


def test_reverse_charge_credit_and_debit_notes_post_balanced_journals(tenant_a):
    from accounting.models import JournalEntry

    _with_accounting(tenant_a)
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="RCM-JN", hsn_code="9983", gst_rate="18")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="RCM Buyer", state="Karnataka", gstin="29AABCU9603R1ZJ")
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id, "invoice_type": "GST", "is_reverse_charge": True,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant_a.client.post(
        f"/api/v1/sales/invoices/{created.data['id']}/complete/", {"confirm_sales_rcm": True}, format="json"
    ).status_code == 200
    invoice = created.data
    cn = _draft_note(tenant_a.client, "credit", customer, invoice, product, price="100").data
    assert _complete(tenant_a.client, "credit", cn["id"], confirm_price_override=True).status_code == 200
    dn = _draft_note(tenant_a.client, "debit", customer, invoice, product, price="100").data
    assert _complete(tenant_a.client, "debit", dn["id"], confirm_additional_debit=True).status_code == 200
    for source_type, note_id in (("SALES_CREDIT_NOTE", cn["id"]), ("SALES_DEBIT_NOTE", dn["id"])):
        entry = JournalEntry.objects.get(
            company=tenant_a.company, source_type=source_type, source_id=note_id, purpose="COMPLETE",
        )
        lines = list(entry.lines.all())
        assert sum(line.debit for line in lines) == sum(line.credit for line in lines) > 0


# ---------------------------------------------------------------- CN-04 / DN-05 additional charges


def _invoice_with_freight(tenant, freight="100"):
    product = make_product(tenant.company, sku="CN-FRT", hsn_code="8517")
    customer = make_customer(tenant.company, name="Freight Customer")
    add_stock(tenant, product, "50")
    inv = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "5", "unit_price": "100"}],
        additional_charges=freight, charges_hsn="9965", charges_gst_rate="18",
    )
    done = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    return product, customer, inv


def test_credit_note_can_credit_freight_up_to_what_was_billed(tenant_a):
    # The invoice is completed before books are switched on: an invoice whose freight carries
    # GST cannot be posted to the ledger today (header tax includes the freight tax, lines do not).
    product, customer, invoice = _invoice_with_freight(tenant_a)
    _with_accounting(tenant_a)
    cn = _draft_note(
        tenant_a.client, "credit", customer, invoice, product, price="10",
        additional_charges="60", charges_hsn="9965", charges_gst_rate="18",
    )
    assert cn.status_code == 201, cn.data
    # (1 x 10 + 60 freight) x 1.18 = 82.60, rounded off to the rupee.
    assert Decimal(str(cn.data["grand_total"])) == Decimal("83.00")
    assert _complete(tenant_a.client, "credit", cn.data["id"], confirm_price_override=True).status_code == 200
    from accounting.models import JournalEntry

    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_CREDIT_NOTE", source_id=cn.data["id"], purpose="COMPLETE",
    )
    lines = list(entry.lines.all())
    assert sum(line.debit for line in lines) == sum(line.credit for line in lines) == Decimal("83.00")


def test_credit_note_cannot_credit_more_freight_than_the_invoice_billed(tenant_a):
    product, customer, invoice = _invoice_with_freight(tenant_a, freight="100")
    first = _draft_note(
        tenant_a.client, "credit", customer, invoice, product, price="10",
        additional_charges="70", charges_hsn="9965", charges_gst_rate="18",
    ).data
    assert _complete(tenant_a.client, "credit", first["id"], confirm_price_override=True).status_code == 200
    second = _draft_note(
        tenant_a.client, "credit", customer, invoice, product, price="10",
        additional_charges="70", charges_hsn="9965", charges_gst_rate="18",
    ).data
    refused = _complete(tenant_a.client, "credit", second["id"], confirm_price_override=True)
    assert refused.status_code == 400 and "charges" in str(refused.data).lower()


def test_debit_note_can_bill_freight_not_on_the_original_invoice(tenant_a):
    product, customer, invoice = _invoice_with_freight(tenant_a, freight="0")
    dn = _draft_note(
        tenant_a.client, "debit", customer, invoice, product, price="10",
        additional_charges="40", charges_hsn="9965", charges_gst_rate="18",
    )
    assert dn.status_code == 201, dn.data
    assert Decimal(str(dn.data["grand_total"])) == Decimal("59.00")  # (10 + 40) x 1.18
    assert _complete(tenant_a.client, "debit", dn.data["id"], confirm_additional_debit=True).status_code == 200


# ---------------------------------------------------------------- DEP-04: reports net the contra account


def test_schedule_iii_revenue_nets_sales_against_the_contra_account(tenant_a):
    from accounting.reports import _balances, schedule_iii_profit_and_loss

    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_CONTRA_SALES_ACCOUNT"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["feature_flags", "accounting_enabled"])
    product = make_product(tenant_a.company, sku="CN-SCH3", hsn_code="8517")
    customer = make_customer(tenant_a.company)
    invoice = _completed_invoice(tenant_a, customer, product)  # 500 taxable
    cn = _draft_note(tenant_a.client, "credit", customer, invoice, product, price="100").data  # 100 taxable
    assert _complete(tenant_a.client, "credit", cn["id"], confirm_price_override=True).status_code == 200
    result = schedule_iii_profit_and_loss(_balances(tenant_a.company))
    revenue = next(
        line for section in result["sections"] for line in section["lines"]
        if line["key"] == "revenue_from_operations"
    )
    assert revenue["amount"] == Decimal("400.00")
    assert {a["code"] for a in revenue["accounts"]} == {"4100", "4110"}


# ---------------------------------------------------------------- CN-07: the 30 November limit


def test_credit_note_30_november_boundary(tenant_a):
    """An invoice dated in FY 2025-26 can be credited up to 30 Nov 2026, not after (unless the annual
    return was filed earlier: see test_credit_note_stops_at_annual_return_filing_date)."""
    product = make_product(tenant_a.company, sku="CN-NOV", hsn_code="8517")
    customer = make_customer(tenant_a.company)
    add_stock(tenant_a, product, "50")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}],
        invoice_date="2026-02-10",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    on_the_day = _draft_note(tenant_a.client, "credit", customer, inv, product, price="10", note_date="2026-11-30").data
    assert _complete(tenant_a.client, "credit", on_the_day["id"], confirm_price_override=True).status_code == 200
    too_late = _draft_note(tenant_a.client, "credit", customer, inv, product, price="10", note_date="2026-12-01").data
    refused = _complete(tenant_a.client, "credit", too_late["id"], confirm_price_override=True)
    assert refused.status_code == 400 and "Sec 34(2)" in str(refused.data)


def test_credit_note_stops_at_annual_return_filing_date(tenant_a):
    """QOS-0127: the limit is the earlier of 30 Nov and the day the annual return was filed."""
    product = make_product(tenant_a.company, sku="CN-AR", hsn_code="8517")
    customer = make_customer(tenant_a.company)
    add_stock(tenant_a, product, "50")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}],
        invoice_date="2026-02-10",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    # Cannot be filed before the FY ends, and the reader sees the 30 Nov default.
    early = tenant_a.client.put("/api/v1/reports/gstr9/filing-date/", {"fy": "2025-26", "filed_on": "2026-01-01"}, format="json")
    assert early.status_code == 400
    read = tenant_a.client.get("/api/v1/reports/gstr9/filing-date/?fy=2025-26")
    assert read.status_code == 200 and read.data["filed_on"] is None and read.data["note_deadline"] == "2026-11-30"

    saved = tenant_a.client.put("/api/v1/reports/gstr9/filing-date/", {"fy": "2025-26", "filed_on": "2026-10-15"}, format="json")
    assert saved.status_code == 200 and saved.data["note_deadline"] == "2026-10-15"
    assert AuditEvent.objects.filter(company=tenant_a.company, action="annual_return_filing_date_set").exists()

    after_filing = _draft_note(tenant_a.client, "credit", customer, inv, product, price="10", note_date="2026-10-16").data
    refused = _complete(tenant_a.client, "credit", after_filing["id"], confirm_price_override=True)
    assert refused.status_code == 400 and "15 Oct 2026" in str(refused.data)
    on_filing_day = _draft_note(tenant_a.client, "credit", customer, inv, product, price="10", note_date="2026-10-15").data
    assert _complete(tenant_a.client, "credit", on_filing_day["id"], confirm_price_override=True).status_code == 200

    # A filing date after 30 Nov does not extend the limit; clearing the date restores the default.
    tenant_a.client.put("/api/v1/reports/gstr9/filing-date/", {"fy": "2025-26", "filed_on": "2027-01-10"}, format="json")
    late = _draft_note(tenant_a.client, "credit", customer, inv, product, price="10", note_date="2026-12-01").data
    assert _complete(tenant_a.client, "credit", late["id"], confirm_price_override=True).status_code == 400
    cleared = tenant_a.client.put("/api/v1/reports/gstr9/filing-date/", {"fy": "2025-26", "filed_on": None}, format="json")
    assert cleared.data["filed_on"] is None


def test_filing_date_is_owner_manager_accountant_only(tenant_a):
    viewer = _client_for(tenant_a, CompanyUser.Role.VIEWER, email="v-ar@alpha.test")
    resp = viewer.put("/api/v1/reports/gstr9/filing-date/", {"fy": "2025-26", "filed_on": "2026-10-15"}, format="json")
    assert resp.status_code in (400, 403)


# ---------------------------------------------------------------- purchase side permissions


def test_accountant_can_draft_and_complete_purchase_notes(tenant_a):
    """The Accountant preset holds can_create_purchases, so purchase notes need no role carve-out."""
    from tests.conftest import make_supplier

    accountant = _client_for(
        tenant_a, CompanyUser.Role.ACCOUNTANT, email="acct6@alpha.test", can_create_purchases=True,
    )
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PN-ACC", hsn_code="8517")
    for kind in ("credit", "debit"):
        resp = accountant.post(
            f"/api/v1/purchases/{kind}-notes/",
            {"supplier": supplier.id, "reason": "CORRECTION_OF_INVOICE",
             "items": [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "18"}]},
            format="json",
        )
        assert resp.status_code == 201, resp.data
