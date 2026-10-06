"""API rules for the remaining vertical-module defects."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from accounting.models import Account, JournalEntry
from accounting.services import seed_chart_of_accounts
from accounts.models import CompanyUser
from contracts.models import Contract
from crm.models import Campaign, Opportunity, ReferralReward
from crm.pipeline import capture_lead
from masters.models import Product
from payroll.models import Employee, PaySlip
from sales.models import SalesCreditNote, SalesInvoice
from support.models import VendorTicketShare
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product
from tests.test_growth_os import _flags
from workshop.models import ServiceBay

pytestmark = pytest.mark.django_db


def _grant(company, **flags):
    company.feature_flags = {**(company.feature_flags or {}), **flags}
    company.save(update_fields=["feature_flags"])


def test_bug_prj_003_bad_ids_are_400_and_close_still_blocks_unbilled(tenant_a):
    _grant(tenant_a.company, ENABLE_PROJECTS=True)
    customer = make_customer(tenant_a.company)
    service = make_product(tenant_a.company, sku="PRJ-SVC", product_type=Product.ProductType.SERVICE)
    bad_customer = tenant_a.client.post(
        "/api/v1/projects/", {"customer": "abc", "name": "Site"}, format="json",
    )
    assert bad_customer.status_code == 400, bad_customer.data
    created = tenant_a.client.post(
        "/api/v1/projects/", {"customer": customer.id, "name": "Site"}, format="json",
    )
    assert created.status_code == 201, created.data
    project_id = created.data["id"]
    bad_amount = tenant_a.client.post(
        f"/api/v1/projects/{project_id}/milestones/",
        {"name": "Foundation", "amount": "nope", "service_product": service.id},
        format="json",
    )
    assert bad_amount.status_code == 400, bad_amount.data
    bad_product = tenant_a.client.post(
        f"/api/v1/projects/{project_id}/milestones/",
        {"name": "Foundation", "amount": "100.00", "service_product": "abc"},
        format="json",
    )
    assert bad_product.status_code == 400, bad_product.data
    added = tenant_a.client.post(
        f"/api/v1/projects/{project_id}/milestones/",
        {
            "name": "Foundation",
            "amount": "100.00",
            "service_product": service.id,
            "target_completion_date": "2026-12-01",
        },
        format="json",
    )
    assert added.status_code == 200, added.data
    milestone = added.data["milestones"][0]
    edited = tenant_a.client.post(
        f"/api/v1/projects/{project_id}/milestones/{milestone['id']}/edit/",
        {"name": "Foundation revised", "amount": "120.00", "target_completion_date": "2026-12-15"},
        format="json",
    )
    assert edited.status_code == 200, edited.data
    revised = edited.data["milestones"][0]
    assert revised["name"] == "Foundation revised"
    assert str(revised["target_completion_date"]) == "2026-12-15"
    blocked = tenant_a.client.post(f"/api/v1/projects/{project_id}/close/")
    assert blocked.status_code == 400
    assert "invoice" in str(blocked.data).lower()


def test_bug_wrk_003_004_005_and_ui_013_job_card_rules(tenant_a):
    _grant(tenant_a.company, ENABLE_WORKSHOP=True)
    customer = make_customer(tenant_a.company)
    part = make_product(tenant_a.company, sku="WRK-PART")
    labour = make_product(
        tenant_a.company, sku="WRK-LAB", product_type=Product.ProductType.SERVICE,
    )
    bay = ServiceBay.objects.create(company=tenant_a.company, name="Bay 1")
    start = timezone.now().replace(microsecond=0)
    end = start + timedelta(hours=2)
    created = tenant_a.client.post(
        "/api/v1/workshop/job-cards/",
        {
            "customer": customer.id,
            "complaint": "Knock",
            "registration_no": "KA01AB1234",
            "vehicle_model": "Ace",
            "odometer_reading": "12000.5",
            "service_bay": bay.id,
            "scheduled_start": start.isoformat(),
            "scheduled_end": end.isoformat(),
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["registration_no"] == "KA01AB1234"
    assert created.data["vehicle_model"] == "Ace"
    job_id = created.data["id"]
    negative = tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "PART", "product": part.id, "quantity": "-1", "unit_price": "10"},
        format="json",
    )
    assert negative.status_code == 400, negative.data
    before = JournalEntry.objects.filter(company=tenant_a.company).count()
    line = tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {
            "kind": "LABOUR",
            "product": labour.id,
            "quantity": "2",
            "unit_price": "150.00",
            "labour_minutes": 45,
            "technician_commission_percent": "10",
        },
        format="json",
    )
    assert line.status_code == 200, line.data
    stored = line.data["lines"][0]
    assert stored["labour_minutes"] == 45
    assert stored["commission_amount"] == "30.00"
    assert JournalEntry.objects.filter(company=tenant_a.company).count() == before
    other = tenant_a.client.post(
        "/api/v1/workshop/job-cards/",
        {"customer": customer.id, "complaint": "Second"},
        format="json",
    )
    clash = tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{other.data['id']}/schedule/",
        {
            "service_bay": bay.id,
            "scheduled_start": (start + timedelta(minutes=30)).isoformat(),
            "scheduled_end": (end + timedelta(hours=1)).isoformat(),
        },
        format="json",
    )
    assert clash.status_code == 400
    assert "bay" in str(clash.data).lower()


def test_bug_mfg_006_bom_cycle_is_refused(tenant_a):
    finished = make_product(tenant_a.company, sku="MFG-FG")
    child = make_product(tenant_a.company, sku="MFG-CHILD")
    parent = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": finished.id,
            "name": "Finished",
            "status": "ACTIVE",
            "lines": [{"component": child.id, "qty": "1"}],
        },
        format="json",
    )
    assert parent.status_code == 201, parent.data
    cycle = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": child.id,
            "name": "Loops back",
            "status": "ACTIVE",
            "lines": [{"component": finished.id, "qty": "1"}],
        },
        format="json",
    )
    assert cycle.status_code == 400, cycle.data


def test_bug_mfg_001_issue_posts_wip_only_when_books_are_on(tenant_a):
    company = tenant_a.company
    finished = make_product(company, sku="WIP-FG")
    component = make_product(company, sku="WIP-COMP", purchase_price="80")
    add_stock(tenant_a, component, "10", unit_cost="80")
    bom = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": finished.id,
            "name": "WIP BOM",
            "status": "ACTIVE",
            "lines": [{"component": component.id, "qty": "2"}],
        },
        format="json",
    )
    assert bom.status_code == 201, bom.data
    quiet = tenant_a.client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": bom.data["id"], "qty": "1"},
        format="json",
    )
    released = tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{quiet.data['id']}/release/")
    assert released.status_code == 200, released.data
    assert not JournalEntry.objects.filter(
        company=company, source_type="WORK_ORDER", purpose="RELEASE",
    ).exists()
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    posted = tenant_a.client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": bom.data["id"], "qty": "1"},
        format="json",
    )
    done = tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{posted.data['id']}/release/")
    assert done.status_code == 200, done.data
    entry = JournalEntry.objects.get(
        company=company, source_type="WORK_ORDER", source_id=posted.data["id"], purpose="RELEASE",
    )
    codes = {line.account.code: (line.debit, line.credit) for line in entry.lines.all()}
    assert codes["1450"][0] == Decimal("160.00")
    assert codes["1400"][1] == Decimal("160.00")


def _employee(tenant, code, **extra):
    fields = {
        "salary": Decimal("10000.00"),
        "tax_regime": Employee.TaxRegime.NEW,
        "pt_state": "Delhi",
        "pf_applicable": False,
        "esi_applicable": False,
    }
    fields.update(extra)
    return Employee.objects.create(
        company=tenant.company,
        name=code,
        code=code,
        created_by=tenant.owner,
        updated_by=tenant.owner,
        **fields,
    )


def test_bug_prl_003_disbursement_requires_a_bank_or_explicit_cash(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    _employee(tenant_a, "CASH-1", salary=Decimal("4000.00"))
    run = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-04"}, format="json")
    assert run.status_code == 201, run.data
    run_id = run.data["id"]
    missing = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/", {}, format="json")
    assert missing.status_code == 400
    assert "cash" in str(missing.data).lower()
    bank = Account.objects.get(company=tenant_a.company, code="1500")
    done = tenant_a.client.post(
        f"/api/v1/payroll/pay-runs/{run_id}/complete/",
        {"bank_account_id": bank.id},
        format="json",
    )
    assert done.status_code == 200, done.data
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run_id, purpose="PAYROLL",
    )
    codes = {line.account.code: (line.debit, line.credit) for line in entry.lines.all()}
    assert codes["1500"][1] == Decimal(done.data["slips"][0]["net"])
    assert "1100" not in codes


def test_bug_prl_004_advances_arrears_and_bonus(tenant_a):
    employee = _employee(tenant_a, "COMP-1", salary=Decimal("10000.00"), pf_applicable=True)
    run = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-05"}, format="json")
    run_id = run.data["id"]
    for kind, amount in (("ARREAR", "2000"), ("BONUS", "500"), ("ADVANCE", "100")):
        added = tenant_a.client.post(
            f"/api/v1/payroll/pay-runs/{run_id}/components/",
            {"employee": employee.id, "kind": kind, "amount": amount},
            format="json",
        )
        assert added.status_code == 201, added.data
    done = tenant_a.client.post(
        f"/api/v1/payroll/pay-runs/{run_id}/complete/",
        {"pay_from_cash": True},
        format="json",
    )
    assert done.status_code == 200, done.data
    slip = PaySlip.objects.get(pay_run_id=run_id, employee=employee)
    assert slip.pf_employee == Decimal("1440.00")
    assert slip.gross == Decimal("12500.00")
    statutory = slip.pf_employee + slip.esi_employee + slip.pt_amount + slip.tds_amount
    assert slip.deductions == statutory + Decimal("100.00")
    assert slip.net == slip.gross - slip.deductions


def test_bug_prl_001_pf_admin_floor(tenant_a):
    _employee(
        tenant_a, "PF-1", salary=Decimal("15000.00"), pf_applicable=True,
    )
    run = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-06"}, format="json")
    done = tenant_a.client.post(
        f"/api/v1/payroll/pay-runs/{run.data['id']}/complete/",
        {"pay_from_cash": True},
        format="json",
    )
    assert done.status_code == 200, done.data
    slip = PaySlip.objects.get(pay_run_id=run.data["id"])
    assert slip.pf_admin_charges == Decimal("500.00")
    assert slip.pf_employee == Decimal("1800.00")


def test_bug_prl_002_esi_continues_through_the_contribution_period(tenant_a):
    employee = _employee(
        tenant_a, "ESI-1", salary=Decimal("20000.00"), esi_applicable=True,
    )
    april = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-04"}, format="json")
    first = tenant_a.client.post(
        f"/api/v1/payroll/pay-runs/{april.data['id']}/complete/",
        {"pay_from_cash": True},
        format="json",
    )
    assert first.status_code == 200, first.data
    assert PaySlip.objects.get(pay_run_id=april.data["id"]).esi_employee > 0
    employee.salary = Decimal("30000.00")
    employee.save(update_fields=["salary"])
    may = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-05"}, format="json")
    second = tenant_a.client.post(
        f"/api/v1/payroll/pay-runs/{may.data['id']}/complete/",
        {"pay_from_cash": True},
        format="json",
    )
    assert second.status_code == 200, second.data
    assert PaySlip.objects.get(pay_run_id=may.data["id"], employee=employee).esi_employee > 0
    fresh = _employee(
        tenant_a, "ESI-2", salary=Decimal("30000.00"), esi_applicable=True,
    )
    october = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-10"}, format="json")
    opened = tenant_a.client.post(
        f"/api/v1/payroll/pay-runs/{october.data['id']}/complete/",
        {"pay_from_cash": True},
        format="json",
    )
    assert opened.status_code == 200, opened.data
    assert PaySlip.objects.get(pay_run_id=october.data["id"], employee=fresh).esi_employee == 0


def test_bug_cnt_001_expired_contract_does_not_read_as_active(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    yesterday = timezone.localdate() - timedelta(days=1)
    row = Contract.objects.create(
        company=tenant_a.company,
        customer=customer,
        contract_type=Contract.Type.WARRANTY,
        start_date=yesterday - timedelta(days=30),
        end_date=yesterday,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    Contract.objects.filter(pk=row.pk).update(status=Contract.Status.ACTIVE)
    listed = tenant_a.client.get(f"/api/v1/contracts/{row.pk}/")
    assert listed.status_code == 200, listed.data
    assert listed.data["status"] == "EXPIRED"


def test_bug_cnt_002_schedule_creates_a_draft_invoice(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="AMC-1", product_type=Product.ProductType.SERVICE)
    today = timezone.localdate()
    created = tenant_a.client.post(
        "/api/v1/contracts/",
        {
            "customer": customer.id,
            "product": product.id,
            "contract_type": "AMC",
            "start_date": str(today),
            "end_date": str(today + timedelta(days=60)),
            "value": "500.00",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    scheduled = tenant_a.client.post(
        f"/api/v1/contracts/{created.data['id']}/create-schedule/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cnt-002",
    )
    assert scheduled.status_code in (200, 201), scheduled.data
    invoice = SalesInvoice.objects.get(pk=scheduled.data["invoice"])
    assert invoice.status == SalesInvoice.Status.DRAFT


def test_bug_cmp_002_credit_note_action_returns_a_draft_id(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="CMP-1")
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "QUALITY", "description": "Leak"},
        format="json",
    )
    complaint_id = created.data["id"]
    tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "INSPECTING"}, format="json",
    )
    invoice = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
    )
    tenant_a.client.patch(
        f"/api/v1/complaints/{complaint_id}/", {"source_invoice": invoice["id"]}, format="json",
    )
    tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "APPROVED"}, format="json",
    )
    credit = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/",
        {"items": [{
            "product": product.id,
            "quantity": "1",
            "unit_price": "10",
            "source_item": invoice["items"][0]["id"],
        }]},
        format="json",
    )
    assert credit.status_code == 201, credit.data
    assert credit.data["id"]
    note = SalesCreditNote.objects.get(pk=credit.data["id"])
    assert note.status == SalesCreditNote.Status.DRAFT


def test_bug_crm_003_005_won_needs_a_customer_and_drafts_an_invoice(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, phone="9000007711")
    product = make_product(tenant_a.company, sku="CRM-INV", product_type=Product.ProductType.SERVICE, gst_rate="0")
    bare = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "No buyer", "amount": "50", "stage": "OPEN"},
        format="json",
    )
    assert bare.status_code == 201, bare.data
    won = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{bare.data['id']}/",
        {"stage": "WON"},
        format="json",
    )
    assert won.status_code == 400, won.data
    deal = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "Buyer", "amount": "80", "stage": "WON", "customer": customer.id},
        format="json",
    )
    assert deal.status_code == 201, deal.data
    drafted = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{deal.data['id']}/draft-invoice/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "0"}]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="crm-005",
    )
    assert drafted.status_code == 201, drafted.data
    invoice = SalesInvoice.objects.get(pk=drafted.data["id"])
    assert invoice.status == SalesInvoice.Status.DRAFT


def test_bug_crm_001_002_percent_uses_invoices_and_paid_drafts_a_note(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Referrer", phone="9000008811")
    buyer = make_customer(tenant_a.company, name="Buyer", phone="9000008812")
    product = make_product(
        tenant_a.company, sku="REF-PCT", product_type=Product.ProductType.SERVICE,
        gst_rate="0", purchase_price="0",
    )
    for person, price in ((referrer, "50"), (buyer, "400")):
        draft = create_draft_invoice(
            tenant_a, person,
            [{"product": product.id, "quantity": "1", "unit_price": price, "gst_rate": "0"}],
            invoice_type="NON_GST",
        )
        completed = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
        assert completed.status_code == 200, completed.data
    issued = tenant_a.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": referrer.id, "reward_type": "PERCENT", "reward_value": "10"},
        format="json",
    )
    assert issued.status_code == 201, issued.data
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Buyer", phone="9000008812",
        referral_code=issued.data["code"],
    )
    opportunity = Opportunity.objects.create(
        company=tenant_a.company,
        lead=lead,
        customer=buyer,
        title="Referred",
        amount=Decimal("999.00"),
        stage=Opportunity.Stage.OPEN,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    marked = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity.id}/",
        {"stage": "WON"},
        format="json",
    )
    assert marked.status_code == 200, marked.data
    reward = ReferralReward.objects.get(opportunity=opportunity)
    assert reward.reward_amount == Decimal("40.00")
    approved = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/")
    assert approved.status_code == 200, approved.data
    paid = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert paid.status_code == 200, paid.data
    reward.refresh_from_db()
    assert reward.reward_status == ReferralReward.Status.PAID
    note = SalesCreditNote.objects.get(pk=reward.credit_note_id)
    assert note.status == SalesCreditNote.Status.DRAFT


def test_bug_crm_004_campaign_can_be_edited_and_labels_invoice_revenue(tenant_a):
    _flags(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/crm/campaigns/",
        {"name": "Monsoon", "campaign_type": "DIGITAL", "budget": "10"},
        format="json",
    )
    assert created.status_code == 201, created.data
    edited = tenant_a.client.patch(
        f"/api/v1/crm/campaigns/{created.data['id']}/",
        {"name": "Monsoon revised"},
        format="json",
    )
    assert edited.status_code == 200, edited.data
    assert edited.data["name"] == "Monsoon revised"
    customer = make_customer(tenant_a.company, phone="9000009911")
    campaign = Campaign.objects.get(pk=created.data["id"])
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Lead", phone="9000009912", campaign=campaign.id,
    )
    Opportunity.objects.create(
        company=tenant_a.company, lead=lead, customer=customer, title="Open deal",
        amount=Decimal("500"), stage=Opportunity.Stage.WON, created_by=tenant_a.owner,
    )
    funnel = tenant_a.client.get(f"/api/v1/crm/campaigns/{campaign.id}/funnel/")
    assert funnel.status_code == 200, funnel.data
    assert funnel.data["rows"][0]["revenue_source"] == "no_completed_invoice"
    assert Decimal(funnel.data["revenue"]) == 0


@override_settings(VENDOR_COMPANY_ID="")
def test_bug_sup_003_share_without_a_vendor_is_400(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/support/tickets/",
        {"customer": customer.id, "subject": "Share me", "category": "NUMBER_MISMATCH"},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["category"] == "NUMBER_MISMATCH"
    assert created.data["share_available"] is False
    shared = tenant_a.client.post(f"/api/v1/support/tickets/{created.data['id']}/share/", {}, format="json")
    assert shared.status_code == 400
    assert "vendor" in str(shared.data).lower()


def test_bug_sup_001_002_reassign_category_and_live_share_status(tenant_a, tenant_b):
    _flags(tenant_a.company)
    _flags(tenant_b.company)
    customer = make_customer(tenant_a.company)
    owner_membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.owner)
    created = tenant_a.client.post(
        "/api/v1/support/tickets/",
        {
            "customer": customer.id,
            "subject": "Mismatch",
            "category": "NUMBER_MISMATCH",
            "assigned_to": owner_membership.id,
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    ticket_id = created.data["id"]
    assert created.data["category"] == "NUMBER_MISMATCH"
    staff_membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    moved = tenant_a.client.patch(
        f"/api/v1/support/tickets/{ticket_id}/",
        {"assigned_to": staff_membership.id},
        format="json",
    )
    assert moved.status_code == 200, moved.data
    assert moved.data["assigned_to"] == staff_membership.id
    with override_settings(VENDOR_COMPANY_ID=str(tenant_b.company.id)):
        shared = tenant_a.client.post(f"/api/v1/support/tickets/{ticket_id}/share/", {}, format="json")
        assert shared.status_code == 200, shared.data
        tenant_a.client.post(
            f"/api/v1/support/tickets/{ticket_id}/transition/",
            {"status": "IN_PROGRESS"},
            format="json",
        )
        copy = VendorTicketShare.objects.get(source_ticket_id=ticket_id)
        assert copy.status == "IN_PROGRESS"
        copy.status = "OPEN"
        copy.save(update_fields=["status"])
        listing = tenant_b.client.get("/api/v1/support/shared/")
    assert listing.status_code == 200, listing.data
    rows = listing.data if isinstance(listing.data, list) else listing.data.get("results", listing.data)
    match = next(row for row in rows if row.get("source_number") == created.data["number"])
    assert match["status"] == "IN_PROGRESS"
