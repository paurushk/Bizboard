"""80-plan sessions S2b / S3 / S4 / S6 — historical snapshot, TB, roles, insight codes."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from accounting.reports import trial_balance
from core.invariants import assert_all_invariants
from ledgers.services import LedgerService
from reporting.services import ReportService
from sales.models import SalesDebitNote, SalesInvoice, SalesReturn
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    make_customer,
    make_product,
)
from tests.test_holistic_remaining import _enable_books, _unwrap
from tests.test_pdf_and_share import _complete

pytestmark = pytest.mark.django_db


def _calendar_month_n(today: date | None = None):
    today = today or date.today()
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    n1 = date(today.year, today.month, 1)
    return start, end, n1


def _apply_role_defaults(company, user, role):
    membership = CompanyUser.objects.get(company=company, user=user)
    membership.role = role
    for field, value in CompanyUser.capability_defaults_for_role(role).items():
        setattr(membership, field, value)
    membership.save()
    return membership


def _tb_foot(tb: dict):
    return (
        Decimal(str(tb["total_debit"])),
        Decimal(str(tb["total_credit"])),
        bool(tb["balanced"]),
    )


def test_closed_month_n_snapshot_unchanged_after_n_plus_1_invoice(tenant_a):
    """S2b: calendar month N TB/aging stay still after an N+1 Complete."""
    from django.utils import timezone

    n_start, n_end, n1_start = _calendar_month_n()
    _enable_books(tenant_a, gstin="29AAAAA0000A1ZY")
    tenant_a.company.gstin_verified_at = timezone.now()
    tenant_a.company.save(update_fields=["gstin_verified_at"])

    product = make_product(tenant_a.company, sku="HIST-N", hsn_code="3004")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=draft["id"]).update(invoice_date=n_start, due_date=n_start)
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert completed.status_code == 200, completed.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])

    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": invoice.customer_id,
            "sales_invoice": invoice.id,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
            "return_date": str(n_start),
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    SalesReturn.objects.filter(pk=ret.data["id"]).update(return_date=n_start)
    done = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.RETURNED

    src = invoice.items.get()
    note = SalesDebitNote.objects.create(
        company=invoice.company,
        customer=invoice.customer,
        sales_invoice=invoice,
        note_date=n_start,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    from sales.notes_services import SalesNotesService

    SalesNotesService.set_debit_note_items(
        note,
        [{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("25"), "source_item": src}],
        tenant_a.owner,
    )
    SalesNotesService.complete_debit_note(note, tenant_a.owner)

    tb_before = trial_balance(tenant_a.company, n_end)
    aging_before = ReportService._aging_total(ReportService.receivables_aging(tenant_a.company, as_of=n_end))
    dash_before = ReportService._company_receivables(tenant_a.company)
    assert tb_before["balanced"] is True
    foot_before = _tb_foot(tb_before)

    pdf = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.id}/pdf/")
    pdf_bytes = b"".join(pdf.streaming_content) if pdf.status_code == 200 else None

    period = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "Month N", "start_date": str(n_start), "end_date": str(n_end)},
        format="json",
    )
    assert period.status_code in (200, 201), period.data
    pid = _unwrap(period.data)["id"]
    closed = tenant_a.client.post(f"/api/v1/accounting/periods/{pid}/close/")
    assert closed.status_code == 200, closed.data

    fetched = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.id}/")
    assert fetched.status_code == 200, fetched.data
    assert _unwrap(fetched.data)["status"] == SalesInvoice.Status.RETURNED

    later = create_draft_invoice(
        tenant_a,
        invoice.customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50.00", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=later["id"]).update(invoice_date=n1_start)
    later_done = tenant_a.client.post(f"/api/v1/sales/invoices/{later['id']}/complete/")
    assert later_done.status_code == 200, later_done.data

    tb_after = trial_balance(tenant_a.company, n_end)
    aging_after = ReportService._aging_total(ReportService.receivables_aging(tenant_a.company, as_of=n_end))
    assert _tb_foot(tb_after) == foot_before
    assert aging_after == aging_before
    dash_after = ReportService._company_receivables(tenant_a.company)
    assert dash_after != dash_before

    if pdf_bytes is not None:
        pdf_again = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.id}/pdf/")
        assert pdf_again.status_code == 200
        assert b"".join(pdf_again.streaming_content) == pdf_bytes

    backdated = create_draft_invoice(
        tenant_a,
        invoice.customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10.00", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=backdated["id"]).update(invoice_date=n_start)
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{backdated['id']}/complete/")
    assert blocked.status_code in (400, 403, 409, 422), blocked.data


def test_trial_balance_balanced_after_lifecycle_close(tenant_a):
    """S3: TB.balanced after a books-on close with documents."""
    _enable_books(tenant_a, gstin="29AAAAA0000A1ZY")
    data, _product = _complete(tenant_a)
    invoice = SalesInvoice.objects.get(pk=data["id"])
    day = invoice.invoice_date
    period = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "S3 close", "start_date": str(day), "end_date": str(day)},
        format="json",
    )
    assert period.status_code in (200, 201), period.data
    closed = tenant_a.client.post(f"/api/v1/accounting/periods/{_unwrap(period.data)['id']}/close/")
    assert closed.status_code == 200, closed.data
    tb = tenant_a.client.get("/api/v1/accounting/trial-balance/")
    assert tb.status_code == 200, tb.data
    body = _unwrap(tb.data)
    assert body.get("balanced") is True
    debit = body.get("total_debit", body.get("totalDebit"))
    credit = body.get("total_credit", body.get("totalCredit"))
    assert Decimal(str(debit)) == Decimal(str(credit))
    assert_all_invariants(tenant_a.company)


def test_cashier_cannot_complete_return_accountant_cannot_close(tenant_a):
    """S4: SALES_STAFF 403 on return Complete; ACCOUNTANT 403 on period close."""
    _apply_role_defaults(tenant_a.company, tenant_a.staff, CompanyUser.Role.SALES_STAFF)
    _enable_books(tenant_a, gstin="29AAAAA0000A1ZY")
    product = make_product(tenant_a.company, sku="S4-POS", hsn_code="7318")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)

    checkout = tenant_a.staff_client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "items": [{"product": product.id, "quantity": "1", "unit_price": "100.00"}],
            },
            "payment": {"mode": "CASH", "amount": "100.00", "tendered_amount": "100.00"},
        },
        format="json",
    )
    assert checkout.status_code == 201, checkout.data
    payload = checkout.data.get("data") if isinstance(checkout.data.get("data"), dict) else checkout.data
    invoice_id = payload.get("id") or (payload.get("invoice") or {}).get("id")
    if not invoice_id:
        invoice_id = SalesInvoice.objects.filter(company=tenant_a.company).order_by("-id").first().id
    invoice = SalesInvoice.objects.get(pk=invoice_id)
    assert invoice.number
    outstanding = LedgerService.sales_invoice_outstanding(invoice)
    assert outstanding == 0

    ret = tenant_a.staff_client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    denied = tenant_a.staff_client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert denied.status_code == 403, denied.data

    owner_done = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert owner_done.status_code == 200, owner_done.data
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.RETURNED

    invited = tenant_a.client.post(
        "/api/v1/company/users/",
        {
            "email": "accountant@s4.test",
            "password": "StrongPass123!",
            "full_name": "S4 Accountant",
            "role": "ACCOUNTANT",
        },
        format="json",
    )
    assert invited.status_code == 201, invited.data
    acct = User.objects.get(email="accountant@s4.test")
    acct_client = APIClient()
    acct_client.force_authenticate(user=acct)

    tb = acct_client.get("/api/v1/accounting/trial-balance/")
    assert tb.status_code == 200, tb.data
    assert _unwrap(tb.data).get("balanced") is True

    day = date.today()
    period = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "S4 window", "start_date": str(day), "end_date": str(day)},
        format="json",
    )
    assert period.status_code in (200, 201), period.data
    pid = _unwrap(period.data)["id"]
    acct_close = acct_client.post(f"/api/v1/accounting/periods/{pid}/close/")
    assert acct_close.status_code == 403, acct_close.data
    owner_close = tenant_a.client.post(f"/api/v1/accounting/periods/{pid}/close/")
    assert owner_close.status_code == 200, owner_close.data


def test_attention_residual_row_has_stable_code_and_dunning_walks(tenant_a):
    """S6: residual attention `code` + dunning eligible includes RETURNED+residual."""
    from insights.attention import build_attention_rows
    from payments.dunning import eligible_invoices
    from sales.notes_services import SalesNotesService

    data, product = _complete(tenant_a)
    invoice = SalesInvoice.objects.get(pk=data["id"])
    invoice.due_date = date.today() - timedelta(days=10)
    invoice.save(update_fields=["due_date"])

    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": invoice.customer_id,
            "sales_invoice": invoice.id,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200

    src = invoice.items.get()
    note = SalesDebitNote.objects.create(
        company=invoice.company,
        customer=invoice.customer,
        sales_invoice=invoice,
        note_date=invoice.invoice_date,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    SalesNotesService.set_debit_note_items(
        note,
        [{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("25"), "source_item": src}],
        tenant_a.owner,
    )
    SalesNotesService.complete_debit_note(note, tenant_a.owner)

    feed = tenant_a.client.get("/api/v1/insights/attention/")
    assert feed.status_code == 200, feed.data
    rows = feed.data.get("rows") or []
    residual = [r for r in rows if r.get("code") == "AR_RESIDUAL_AFTER_RETURN"]
    assert residual, rows
    assert residual[0]["code"] == "AR_RESIDUAL_AFTER_RETURN"
    assert str(invoice.id) in str(residual[0].get("action_href") or "")

    built = [r for r in build_attention_rows(tenant_a.company) if r.get("code") == "AR_RESIDUAL_AFTER_RETURN"]
    assert built and set(residual[0]).issuperset({"code", "title", "reason", "action_href"})

    dash = ReportService._company_receivables(tenant_a.company)
    aging = ReportService._aging_total(ReportService.receivables_aging(tenant_a.company))
    ledger = LedgerService.sales_invoice_outstanding(SalesInvoice.objects.get(pk=invoice.pk))
    assert dash == aging == ledger
    assert ledger > 0

    eligible_ids = {inv.id for inv in eligible_invoices(tenant_a.company, as_of=date.today())}
    assert invoice.id in eligible_ids
