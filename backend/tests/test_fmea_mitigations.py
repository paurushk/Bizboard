"""Oracles for the scored FMEA mitigations (TC-FMEA-001 through 013)."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.models import Notification
from payroll.models import Employee, PayRun
from payroll.services import complete_pay_run
from reporting.gst_periods import soft_close_period
from reporting.gst_returns import build_gstr1
from sales.models import SalesCreditNote, SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

_WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def _code(resp) -> str | None:
    err = resp.data.get("error") if isinstance(resp.data, dict) else None
    if isinstance(err, dict):
        return err.get("code")
    return None


def test_tc_fmea_001_books_off_price_edit_respects_soft_closed_period(tenant_a):
    tenant_a.company.accounting_enabled = False
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="FMEA-001", gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
    )
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert completed.status_code == 200, completed.data
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data
    before = detail["grand_total"]
    period = str(detail["invoice_date"])[:7]
    soft_close_period(tenant_a.company, period, tenant_a.owner)
    item = detail["items"][0]
    patched = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": detail.get("amend_revision", 0),
            "items": [{
                "id": item["id"],
                "product": product.id,
                "quantity": "1",
                "unit_price": "250.00",
                "gst_rate": "18",
            }],
        },
        format="json",
    )
    assert patched.status_code == 400, patched.data
    assert _code(patched) == "closed_period"
    after = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data
    assert after["grand_total"] == before


def test_tc_fmea_002_blank_party_assumption_is_stamped_and_listed(tenant_a):
    tenant_a.company.assume_local_state_for_blank_party = True
    tenant_a.company.save(update_fields=["assume_local_state_for_blank_party"])
    product = make_product(tenant_a.company, sku="FMEA-002", gst_rate="18")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="", gstin="")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
    )
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert completed.status_code == 200, completed.data
    row = SalesInvoice.objects.get(pk=inv["id"])
    assert row.pos_assumed_local is True
    period = row.invoice_date.strftime("%Y-%m")
    issues = build_gstr1(tenant_a.company, period)["issues"]
    assert any(issue["code"] == "POS_ASSUMED_LOCAL" and issue["document_id"] == row.pk for issue in issues)

    known = make_customer(tenant_a.company, name="GSTIN Co", state="", gstin="29AAAAA0000A1ZY", phone="9000000029")
    known_inv = create_draft_invoice(
        tenant_a, known,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
    )
    known_done = tenant_a.client.post(f"/api/v1/sales/invoices/{known_inv['id']}/complete/")
    assert known_done.status_code == 200, known_done.data
    assert SalesInvoice.objects.get(pk=known_inv["id"]).pos_assumed_local is False


def test_tc_fmea_004_mark_paid_does_not_draft_a_product_credit_note(tenant_a):
    from crm.models import ReferralReward
    from crm.pipeline import capture_lead

    from masters.models import Product

    from .test_growth_os import _flags

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, phone="9000000041")
    invoices = []
    for sku, amount in (("FMEA-004A", "400"), ("FMEA-004B", "900")):
        product = make_product(
            tenant_a.company, sku=sku, product_type=Product.ProductType.SERVICE,
        )
        payload = create_draft_invoice(
            tenant_a, customer,
            [{"product": product.id, "quantity": "1", "unit_price": amount, "gst_rate": "0"}],
            invoice_type="NON_GST",
        )
        row = SalesInvoice.objects.get(pk=payload["id"])
        from sales.services import SalesService

        SalesService.complete(row, tenant_a.owner)
        invoices.append(row)
    first, second = invoices
    issued = tenant_a.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": customer.id, "reward_type": "FLAT", "reward_value": "40"},
        format="json",
    )
    assert issued.status_code == 201, issued.data
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Referred", phone="9000000042",
        referral_code=issued.data["code"],
    )
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/",
        {"won": True, "amount": "100"},
        format="json",
    )
    reward = ReferralReward.objects.get(opportunity_id=converted.data["opportunity"]["id"])
    tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/")
    before = SalesCreditNote.objects.filter(company=tenant_a.company).count()
    paid = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert paid.status_code == 200, paid.data
    assert SalesCreditNote.objects.filter(company=tenant_a.company).count() == before + 1
    assert first.credit_notes.count() == 0
    note = second.credit_notes.get()
    assert note.status == SalesCreditNote.Status.DRAFT
    reward.refresh_from_db()
    assert reward.credit_note_id == note.id


def test_tc_fmea_005_complaint_document_waits_for_approval(tenant_a):
    from .test_growth_os import _flags

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, phone="9000000051")
    product = make_product(tenant_a.company, sku="FMEA-005")
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "QUALITY", "description": "Leak"},
        format="json",
    )
    assert created.status_code == 201, created.data
    complaint_id = created.data["id"]
    tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "INSPECTING"}, format="json",
    )
    invoice = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/complaints/{complaint_id}/", {"source_invoice": invoice["id"]}, format="json",
    )
    source_item = invoice["items"][0]["id"]
    early = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "10", "source_item": source_item}]},
        format="json",
    )
    assert early.status_code == 400
    assert "approved" in str(early.data).lower()
    assert SalesCreditNote.objects.filter(company=tenant_a.company).count() == 0
    approved = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "APPROVED"}, format="json",
    )
    assert approved.status_code == 200, approved.data
    made = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "10", "source_item": source_item}]},
        format="json",
    )
    assert made.status_code == 201, made.data


def _employee(tenant, **extra):
    defaults = dict(
        company=tenant.company,
        name="Old Regime",
        code="FMEA-OLD",
        salary=Decimal("20000.00"),
        tax_regime=Employee.TaxRegime.OLD,
        tds_rate=Decimal("0"),
        created_by=tenant.owner,
        updated_by=tenant.owner,
    )
    defaults.update(extra)
    return Employee.objects.create(**defaults)


def test_tc_fmea_006_old_regime_without_a_rate_cannot_complete(tenant_a):
    _employee(tenant_a)
    run = PayRun.objects.create(
        company=tenant_a.company, period="2026-08", status=PayRun.Status.DRAFT,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError, match="Old-regime"):
        complete_pay_run(run, tenant_a.owner, pay_from_cash=True)
    assert run.slips.count() == 0

    employee = Employee.objects.get(company=tenant_a.company, code="FMEA-OLD")
    employee.tds_rate = Decimal("10")
    employee.save(update_fields=["tds_rate"])
    complete_pay_run(run, tenant_a.owner, pay_from_cash=True)
    slip = run.slips.get()
    assert slip.tds_amount == Decimal("2000.00")


def test_tc_fmea_007_books_health_flags_a_pay_run_finished_while_books_were_off(tenant_a):
    from accounting.services import BooksHealthService

    tenant_a.company.accounting_enabled = False
    tenant_a.company.save(update_fields=["accounting_enabled"])
    _employee(tenant_a, code="FMEA-NEW", tax_regime=Employee.TaxRegime.NEW, name="New Regime")
    run = PayRun.objects.create(
        company=tenant_a.company, period="2026-09", status=PayRun.Status.DRAFT,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    complete_pay_run(run, tenant_a.owner, pay_from_cash=True)
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    alerts = BooksHealthService.control_balances(tenant_a.company)["alerts"]
    assert any(alert["code"] == "PAY_RUN_UNPOSTED" and alert["severity"] == "error" for alert in alerts)


def test_tc_fmea_008_work_order_complete_copy_says_cost_lands_on_the_primary_good():
    page = (_WEB / "pages" / "manufacturing" / "WorkOrdersPage.tsx").read_text(encoding="utf-8")
    english = (_WEB / "i18n" / "en.ts").read_text(encoding="utf-8")
    hindi = (_WEB / "i18n" / "hi.ts").read_text(encoding="utf-8")
    assert "woAbsorbsAllIssueCost" in page
    assert "primary finished good" in english
    assert "woAbsorbsAllIssueCost" in hindi


def test_tc_fmea_009_production_without_rls_is_logged_and_does_not_fail_the_sweep(tenant_a, caplog):
    from django.db import connections
    from django.test import override_settings

    from core.tasks import nightly_invariants_task

    with override_settings(DJANGO_ENV="production", POSTGRES_RLS_ENABLED=False):
        with patch.object(connections["default"], "vendor", "postgresql"):
            with caplog.at_level(logging.ERROR, logger="core.tasks"):
                result = nightly_invariants_task()
    assert result["failed"] == 0
    assert result["rls_enabled"] is False
    assert "Postgres RLS is off in production" in caplog.text


def test_tc_fmea_010_a_failed_invariant_notifies_the_owner_in_app(tenant_a):
    from inventory.models import StockBalance

    from core.tasks import nightly_invariants_task

    product = make_product(tenant_a.company, sku="FMEA-010")
    add_stock(tenant_a, product, "10", unit_cost="60")
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    balance.on_hand = Decimal("999999")
    balance.save(update_fields=["on_hand"])
    result = nightly_invariants_task()
    assert result["failed"] >= 1
    note = Notification.objects.filter(
        company=tenant_a.company,
        channel=Notification.Channel.IN_APP,
        subject="Books check failed",
    )
    assert note.exists()
    assert "inventory.balance_equals_movements" in note.get().body


def test_tc_fmea_011_cloud_post_requires_opt_in():
    from core.services import whatsapp

    flags = {"ENABLE_WHATSAPP_CLOUD": True}
    with patch.object(whatsapp, "build_feature_flags", return_value=flags), patch.object(
        whatsapp, "_resolve_whatsapp_credentials", return_value=("tok", "12345"),
    ), patch.object(whatsapp.requests, "post") as mock_post:
        result = whatsapp.send_whatsapp_template(
            "919876543210",
            "invoice_ready",
            ["INV-1"],
            company=object(),
            allow_cloud=True,
            opt_in=False,
        )
    assert result.mode == "link"
    mock_post.assert_not_called()


def test_tc_fmea_012_a_stale_queued_pdf_is_requeued_and_the_owner_is_told_once(tenant_a):
    from sales.tasks import requeue_stale_invoice_pdfs

    product = make_product(tenant_a.company, sku="FMEA-012")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, phone="9000000120")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    SalesInvoice.objects.filter(pk=inv["id"]).update(
        pdf_status=SalesInvoice.PdfStatus.QUEUED,
        updated_at=timezone.now() - timedelta(minutes=20),
    )
    cache.delete(f"pdf-stale-notified:{inv['id']}")
    with patch("sales.tasks.generate_invoice_pdf.delay") as delay, patch(
        "core.services.telegram.notify_company_owners",
    ) as notify:
        first = requeue_stale_invoice_pdfs()
        second = requeue_stale_invoice_pdfs()
    assert first["requeued"] == 1
    assert second["requeued"] == 1
    assert delay.call_count == 2
    assert notify.call_count == 1


def test_tc_fmea_013_a_schedule_starting_today_does_not_run_until_next_month(tenant_a):
    from contracts.models import Contract
    from contracts.services import create_contract_schedule

    product = make_product(tenant_a.company, sku="FMEA-013")
    customer = make_customer(tenant_a.company, phone="9000000130")
    today = timezone.localdate()
    contract = Contract.objects.create(
        company=tenant_a.company,
        customer=customer,
        product=product,
        contract_type=Contract.Type.AMC,
        start_date=today,
        end_date=today + timedelta(days=400),
        value=Decimal("1500.00"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    schedule = create_contract_schedule(contract, tenant_a.owner)
    assert schedule.next_run_at.date() > today
    assert schedule.next_run_at.month != today.month or schedule.next_run_at.year != today.year


def test_fmea2_001_pay_run_cancel_refuses_while_books_off(tenant_a, tenant_b):
    from io import StringIO

    from django.core.management import call_command

    from accounting.models import JournalEntry
    from accounting.reports import trial_balance
    from accounting.services import BooksHealthService
    from payroll.services import cancel_pay_run

    tenant_a.company.accounting_enabled = True
    tenant_a.company.feature_flags = {"ENABLE_PAYROLL": True}
    tenant_a.company.save(update_fields=["accounting_enabled", "feature_flags"])
    tenant_b.company.feature_flags = {"ENABLE_PAYROLL": True}
    tenant_b.company.save(update_fields=["feature_flags"])
    _employee(
        tenant_a, code="FMEA2-001", tax_regime=Employee.TaxRegime.NEW, name="Books On",
    )
    run = PayRun.objects.create(
        company=tenant_a.company, period="2026-07", status=PayRun.Status.DRAFT,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    b_journals = JournalEntry.objects.filter(company=tenant_b.company).count()
    complete_pay_run(run, tenant_a.owner, pay_from_cash=True)
    posted = JournalEntry.objects.get(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run.pk,
        purpose="PAYROLL", status=JournalEntry.Status.POSTED,
    )
    tenant_a.company.accounting_enabled = False
    tenant_a.company.save(update_fields=["accounting_enabled"])
    with pytest.raises(BusinessRuleError, match="Turn accounting on"):
        cancel_pay_run(run, tenant_a.owner)
    run.refresh_from_db()
    posted.refresh_from_db()
    assert run.status == PayRun.Status.COMPLETED
    assert posted.status == JournalEntry.Status.POSTED
    assert JournalEntry.objects.filter(company=tenant_b.company).count() == b_journals

    run.status = PayRun.Status.DRAFT
    run.save(update_fields=["status"])
    out = StringIO()
    call_command("repair_orphan_pay_run_journals", "--apply", stdout=out)
    posted.refresh_from_db()
    assert posted.status == JournalEntry.Status.POSTED
    assert f"pay_run={run.pk}" in out.getvalue()
    run.status = PayRun.Status.COMPLETED
    run.save(update_fields=["status"])

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    cancel_pay_run(run, tenant_a.owner)
    run.refresh_from_db()
    posted.refresh_from_db()
    assert run.status == PayRun.Status.DRAFT
    assert posted.status == JournalEntry.Status.REVERSED
    complete_pay_run(run, tenant_a.owner, pay_from_cash=True)
    fresh = JournalEntry.objects.get(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run.pk,
        purpose="PAYROLL", status=JournalEntry.Status.POSTED,
    )
    assert fresh.pk != posted.pk
    slip_net = sum((s.net for s in run.slips.all()), Decimal("0"))
    assert slip_net > 0
    assert fresh.lines.filter(credit=slip_net).exists()
    tb = trial_balance(tenant_a.company)
    assert tb["balanced"] is True
    assert tb["total_debit"] == tb["total_credit"]
    alerts = BooksHealthService.control_balances(tenant_a.company)["alerts"]
    assert not any(alert["code"] == "PAY_RUN_JOURNAL_OPEN" for alert in alerts)
    assert JournalEntry.objects.filter(company=tenant_b.company).count() == b_journals


def test_fmea2_006_cloud_send_same_phone(tenant_a, tenant_b):
    from unittest.mock import MagicMock

    from core.services import whatsapp
    from payments.services import PaymentService

    customer = make_customer(
        tenant_a.company, phone="919876543210", whatsapp_opt_in=True,
    )
    link = PaymentService.create_payment_link(
        company=tenant_a.company, amount=Decimal("100"), customer=customer, provider="sandbox",
        user=tenant_a.owner,
    )
    flags = {"ENABLE_WHATSAPP_CLOUD": True}
    ok = MagicMock(status_code=200, json=lambda: {"messages": [{"id": "wamid.1"}]})
    with patch.object(whatsapp, "build_feature_flags", return_value=flags), patch.object(
        whatsapp, "_resolve_whatsapp_credentials", return_value=("tok", "12345"),
    ), patch.object(whatsapp.requests, "post", return_value=ok) as mock_post:
        plus = PaymentService.share_payment_link(
            link=link, channel="WHATSAPP", recipient="+91 98765 43210", user=tenant_a.owner,
        )
        ten = PaymentService.share_payment_link(
            link=link, channel="WHATSAPP", recipient="9876543210", user=tenant_a.owner,
        )
        other = PaymentService.share_payment_link(
            link=link, channel="WHATSAPP", recipient="+91 90000 00001", user=tenant_a.owner,
        )
    assert getattr(plus, "delivery_mode", None) == "cloud"
    assert getattr(ten, "delivery_mode", None) == "cloud"
    assert getattr(other, "delivery_mode", None) == "link"
    assert mock_post.call_count == 2
    assert Notification.objects.filter(company=tenant_b.company).count() == 0


def test_fmea2_007_complaint_return_xor_credit_note(tenant_a, tenant_b):
    from inventory.models import MovementType, StockMovement

    from sales.models import SalesReturn
    from tests.test_growth_os import _flags

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    _flags(tenant_a.company)
    _flags(tenant_b.company)
    customer = make_customer(tenant_a.company, phone="9000000071")
    product = make_product(tenant_a.company, sku="FMEA2-007", gst_rate="0")
    add_stock(tenant_a, product, "5")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    source_item = done.data["items"][0]["id"]
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "QUALITY", "description": "Leak"},
        format="json",
    )
    assert created.status_code == 201, created.data
    complaint_id = created.data["id"]
    tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "INSPECTING"}, format="json",
    )
    tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "APPROVED"}, format="json",
    )
    tenant_a.client.patch(
        f"/api/v1/complaints/{complaint_id}/", {"source_invoice": inv["id"]}, format="json",
    )
    items = [{"product": product.id, "quantity": "1", "unit_price": "10", "source_item": source_item}]
    made_return = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-return/", {"items": items}, format="json",
    )
    assert made_return.status_code == 201, made_return.data
    blocked = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/", {"items": items}, format="json",
    )
    assert blocked.status_code == 400
    assert SalesReturn.objects.filter(company=tenant_a.company).count() == 1
    assert SalesCreditNote.objects.filter(company=tenant_a.company, sales_return__isnull=True).count() == 0
    completed = tenant_a.client.post(f"/api/v1/sales/returns/{made_return.data['id']}/complete/")
    assert completed.status_code == 200, completed.data
    assert StockMovement.objects.filter(
        company=tenant_a.company, movement_type=MovementType.SALES_RETURN,
    ).count() == 1
    assert SalesCreditNote.objects.filter(
        company=tenant_a.company, sales_return_id=made_return.data["id"],
        status=SalesCreditNote.Status.COMPLETED,
    ).count() == 1
    before = StockMovement.objects.filter(company=tenant_a.company).count()
    rejected = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "QUALITY", "description": "No document"},
        format="json",
    )
    tenant_a.client.post(
        f"/api/v1/complaints/{rejected.data['id']}/transition/",
        {"status": "INSPECTING"}, format="json",
    )
    tenant_a.client.post(
        f"/api/v1/complaints/{rejected.data['id']}/transition/",
        {"status": "REJECTED"}, format="json",
    )
    resolved = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "QUALITY", "description": "Resolved bare"},
        format="json",
    )
    rid = resolved.data["id"]
    tenant_a.client.post(
        f"/api/v1/complaints/{rid}/transition/", {"status": "INSPECTING"}, format="json",
    )
    tenant_a.client.post(
        f"/api/v1/complaints/{rid}/transition/", {"status": "APPROVED"}, format="json",
    )
    tenant_a.client.post(
        f"/api/v1/complaints/{rid}/transition/", {"status": "RESOLVED"}, format="json",
    )
    assert StockMovement.objects.filter(company=tenant_a.company).count() == before
    assert StockMovement.objects.filter(company=tenant_b.company).count() == 0
    assert SalesCreditNote.objects.filter(company=tenant_b.company).count() == 0


def test_fmea2_008_audit_failure_rolls_back(tenant_a):
    from accounting.models import JournalEntry
    from core.services.audit import AuditService
    from inventory.models import MovementType, StockMovement
    from sales.services import SalesService

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="FMEA2-008A", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "40", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    with patch.object(AuditService, "log", side_effect=RuntimeError("audit down")):
        with pytest.raises(RuntimeError, match="audit down"):
            SalesService.complete(invoice, tenant_a.owner)
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.DRAFT
    assert not JournalEntry.objects.filter(
        company=tenant_a.company, source_type="SALES_INVOICE", source_id=invoice.pk,
    ).exists()
    assert not StockMovement.objects.filter(
        company=tenant_a.company, movement_type=MovementType.SALE, reference_id=str(invoice.pk),
    ).exists()


def test_fmea2_008_audit_row_once(tenant_a):
    from core.models import AuditEvent
    from sales.services import SalesService

    product = make_product(tenant_a.company, sku="FMEA2-008B", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "40", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    with patch("sales.handlers._enqueue", side_effect=RuntimeError("pdf")):
        SalesService.complete(invoice, tenant_a.owner)
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.COMPLETED
    events = AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="SalesInvoice", entity_id=str(invoice.pk),
    )
    assert events.filter(description="sales_invoice.completed").count() == 1
    SalesService.cancel(invoice, tenant_a.owner)
    assert events.filter(description="sales_invoice.completed").count() == 1
    assert events.filter(description="sales_invoice.cancelled").count() == 1


def test_fmea2_005_opportunity_total_decimal(tenant_a):
    from crm.models import Opportunity
    from insights.customer_360 import customer_360

    customer = make_customer(tenant_a.company)
    Opportunity.objects.create(
        company=tenant_a.company, customer=customer, title="A", amount=Decimal("0.10"),
        created_by=tenant_a.owner,
    )
    Opportunity.objects.create(
        company=tenant_a.company, customer=customer, title="B", amount=Decimal("0.20"),
        created_by=tenant_a.owner,
    )
    Opportunity.objects.create(
        company=tenant_a.company, customer=customer, title="C", amount=Decimal("0.00"),
        created_by=tenant_a.owner,
    )
    tenant_a.company.feature_flags = {"ENABLE_CUSTOMER_360": True, "ENABLE_CRM": True, "pack_grant": "insurance"}
    tenant_a.company.save(update_fields=["feature_flags"])
    body = customer_360(tenant_a.company, customer)
    assert body["opportunity_total"] == "0.30"
    tenant_a.company.feature_flags = {"ENABLE_CUSTOMER_360": True, "ENABLE_CRM": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    off = customer_360(tenant_a.company, customer)
    assert "opportunity_total" not in off
    page = (_WEB / "pages" / "sales" / "Customer360Page.tsx").read_text(encoding="utf-8")
    assert "opportunityTotal" in page
    assert "sumCustomerOpportunityValue" not in page


def test_fmea2_009_waiting_ticket_sla(tenant_a):
    from insights.growth_metrics import growth_metrics
    from support.models import Ticket

    customer = make_customer(tenant_a.company)
    now = timezone.now()
    Ticket.objects.create(
        company=tenant_a.company, customer=customer, subject="Paused",
        status=Ticket.Status.WAITING,
        sla_due_at=now - timedelta(hours=1),
        waiting_since=now - timedelta(days=2),
        created_by=tenant_a.owner,
    )
    Ticket.objects.create(
        company=tenant_a.company, customer=customer, subject="Already late",
        status=Ticket.Status.WAITING,
        sla_due_at=now - timedelta(days=2),
        waiting_since=now - timedelta(hours=1),
        created_by=tenant_a.owner,
    )
    assert growth_metrics(tenant_a.company)["tickets_past_sla"] == 1


def test_fmea2_012_convert_twice_one_invoice(tenant_a):
    from inventory.models import MovementType, SerialNumber, StockMovement
    from inventory.services import InventoryService
    from sales.services import SalesService
    from workshop.models import JobCard

    tenant_a.company.feature_flags = {"ENABLE_WORKSHOP": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    part = make_product(tenant_a.company, sku="FMEA2-012", gst_rate="0", track_serial=True)
    created = tenant_a.client.post(
        "/api/v1/workshop/job-cards/",
        {"customer": customer.id, "complaint": "Serial missing"},
        format="json",
    )
    assert created.status_code == 201, created.data
    job_id = created.data["id"]
    # a part line holds its stock (BUG-WRK-002), so there must be stock to hold
    add_stock(tenant_a, part, "2")  # one unit per job card below
    assert tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "PART", "product": part.id, "quantity": "1", "unit_price": "100"},
        format="json",
    ).status_code == 200
    blocked = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/convert/")
    assert blocked.status_code == 400
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 0

    wh = InventoryService.default_warehouse(tenant_a.company)
    serial = SerialNumber.objects.create(
        company=tenant_a.company, product=part, warehouse=wh, serial_number="FMEA2-SN",
    )
    lined = tenant_a.client.post(
        "/api/v1/workshop/job-cards/",
        {"customer": customer.id, "complaint": "With serial"},
        format="json",
    )
    job2 = lined.data["id"]
    assert tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job2}/lines/",
        {"kind": "PART", "product": part.id, "quantity": "1", "unit_price": "100", "serial": serial.id},
        format="json",
    ).status_code == 200
    first = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job2}/convert/")
    assert first.status_code == 200, first.data
    second = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job2}/convert/")
    assert second.status_code == 200, second.data
    assert first.data["sales_invoice"] == second.data["sales_invoice"]
    assert second.data["invoice_status"] == "DRAFT"
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    job = JobCard.objects.get(pk=job2)
    assert job.status == JobCard.Status.IN_PROGRESS
    invoice = SalesInvoice.objects.get(pk=first.data["sales_invoice"])
    SalesService.complete(invoice, tenant_a.owner)
    job.refresh_from_db()
    serial.refresh_from_db()
    assert job.status == JobCard.Status.INVOICED
    assert serial.status == SerialNumber.Status.SOLD
    assert StockMovement.objects.filter(
        company=tenant_a.company, product=part, movement_type=MovementType.SALE,
    ).count() == 1
