"""95-plan V3 / V4 / V5 — dump-migrate sweep, second closed month, inventory staff."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from accounts.models import CompanyUser
from accounting.models import Account
from accounting.reports import trial_balance
from core.invariants import assert_all_invariants
from inventory.models import Warehouse
from inventory.services import InventoryService
from reporting.services import ReportService
from sales.models import SalesInvoice, SalesReturn
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product
from tests.test_holistic_80 import _apply_role_defaults, _calendar_month_n, _tb_foot
from tests.test_holistic_remaining import _enable_books, _unwrap

pytestmark = pytest.mark.django_db


def _month_before(start: date) -> tuple[date, date]:
    if start.month == 1:
        year, month = start.year - 1, 12
    else:
        year, month = start.year, start.month - 1
    begin = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return begin, end


def test_v3_g11b_export_migrate_restore_invariants(tenant_a):
    """V3 G-11b — tenant dump, migrate, restore, then INVARIANTS_STRICT sweep."""
    from accounts.tenant_backup import build_export_payload, restore_destroy_in_place

    _enable_books(tenant_a, gstin="29AAAAA0000A1ZY")
    product = make_product(tenant_a.company, sku="G11B", hsn_code="7318")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    assert_all_invariants(tenant_a.company)

    payload = build_export_payload(tenant_a.company)
    call_command("migrate", "--noinput")
    restore_destroy_in_place(
        company=tenant_a.company,
        payload=payload,
        owner=tenant_a.owner,
        confirm_destroy_unbacked=True,
    )
    tenant_a.company.refresh_from_db()
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    assert_all_invariants(tenant_a.company)


def test_v4_n_and_n_minus_1_closed_reject_backdated_complete(tenant_a):
    """V4 — close N−1 and N; N+1 Complete is 200; backdated into either closed month is 4xx;
    RETURNED survives both closes. N as-of snapshot is unchanged after N+1."""
    from django.utils import timezone

    n_start, n_end, n1_start = _calendar_month_n()
    nm1_start, nm1_end = _month_before(n_start)
    _enable_books(tenant_a, gstin="29AAAAA0000A1ZY")
    tenant_a.company.gstin_verified_at = timezone.now()
    tenant_a.company.save(update_fields=["gstin_verified_at"])

    product = make_product(tenant_a.company, sku="HIST-N1", hsn_code="3004")
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
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.RETURNED

    p_nm1 = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "Month N-1", "start_date": str(nm1_start), "end_date": str(nm1_end)},
        format="json",
    )
    assert p_nm1.status_code in (200, 201), p_nm1.data
    closed_nm1 = tenant_a.client.post(
        f"/api/v1/accounting/periods/{_unwrap(p_nm1.data)['id']}/close/"
    )
    assert closed_nm1.status_code == 200, closed_nm1.data

    p_n = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "Month N", "start_date": str(n_start), "end_date": str(n_end)},
        format="json",
    )
    assert p_n.status_code in (200, 201), p_n.data
    closed_n = tenant_a.client.post(
        f"/api/v1/accounting/periods/{_unwrap(p_n.data)['id']}/close/"
    )
    assert closed_n.status_code == 200, closed_n.data

    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.RETURNED

    tb_before = trial_balance(tenant_a.company, n_end)
    aging_before = ReportService._aging_total(ReportService.receivables_aging(tenant_a.company, as_of=n_end))
    assert tb_before["balanced"] is True
    foot_before = _tb_foot(tb_before)

    later = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50.00", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=later["id"]).update(invoice_date=n1_start)
    later_done = tenant_a.client.post(f"/api/v1/sales/invoices/{later['id']}/complete/")
    assert later_done.status_code == 200, later_done.data

    tb_after = trial_balance(tenant_a.company, n_end)
    aging_after = ReportService._aging_total(ReportService.receivables_aging(tenant_a.company, as_of=n_end))
    assert _tb_foot(tb_after) == foot_before
    assert aging_after == aging_before
    # CR-060: live dashboard AR foots to the aging payload it returns (as-of
    # today, so N+1 may be included). Historical as-of N is the pair above.
    dash = ReportService.dashboard(tenant_a.company)
    assert dash["receivables"] == ReportService._aging_total(dash["receivables_aging"])
    assert dash["receivables"] == ReportService._company_receivables(tenant_a.company)

    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.RETURNED

    into_n = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10.00", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=into_n["id"]).update(invoice_date=n_start)
    blocked_n = tenant_a.client.post(f"/api/v1/sales/invoices/{into_n['id']}/complete/")
    assert blocked_n.status_code in (400, 403, 409, 422), blocked_n.data

    into_nm1 = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10.00", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=into_nm1["id"]).update(invoice_date=nm1_start)
    blocked_nm1 = tenant_a.client.post(f"/api/v1/sales/invoices/{into_nm1['id']}/complete/")
    assert blocked_nm1.status_code in (400, 403, 409, 422), blocked_nm1.data


def test_v5_inventory_staff_can_transfer_cannot_journal_or_close(tenant_a):
    """V5 — INVENTORY_STAFF completes a transfer; journal post and period close are 403."""
    _enable_books(tenant_a, gstin="29AAAAA0000A1ZY")
    _apply_role_defaults(tenant_a.company, tenant_a.staff, CompanyUser.Role.INVENTORY_STAFF)
    company = tenant_a.company
    wh1 = InventoryService.default_warehouse(company)
    wh2 = Warehouse.objects.create(company=company, name="V5 Branch", code="V5BR", is_active=True)
    product = make_product(company, sku="V5-XFER")
    add_stock(tenant_a, product, "10")

    staff = tenant_a.staff_client
    tr = staff.post(
        "/api/v1/inventory/transfers/",
        {
            "from_warehouse": wh1.id,
            "to_warehouse": wh2.id,
            "notes": "v5 rebalance",
            "lines": [{"product": product.id, "quantity": "3"}],
        },
        format="json",
    )
    assert tr.status_code == 201, tr.data
    done = staff.post(f"/api/v1/inventory/transfers/{tr.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert InventoryService.available_quantity(company, product, warehouse=wh1) == Decimal("7.000")
    assert InventoryService.available_quantity(company, product, warehouse=wh2) == Decimal("3.000")

    cash = Account.objects.filter(company=company, code="1100").first()
    expense = Account.objects.filter(company=company, code="5200").first()
    assert cash and expense
    journal = staff.post(
        "/api/v1/accounting/journals/",
        {
            "narration": "v5 should 403",
            "lines": [
                {"account": expense.id, "debit": "10", "credit": "0"},
                {"account": cash.id, "debit": "0", "credit": "10"},
            ],
        },
        format="json",
    )
    assert journal.status_code == 403, journal.data

    today = date.today()
    period = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "V5 close", "start_date": str(today), "end_date": str(today)},
        format="json",
    )
    assert period.status_code in (200, 201), period.data
    denied = staff.post(f"/api/v1/accounting/periods/{_unwrap(period.data)['id']}/close/")
    assert denied.status_code == 403, denied.data
    assert_all_invariants(company)


def test_v3_mutation_audit_job_is_advisory():
    """V3 — Linux mutation-audit stays continue-on-error; script targets money/tax/stock."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "\n  mutation-audit:\n" in ci
    block = ci.split("\n  mutation-audit:\n", 1)[1].split("\n  qos-lint:\n", 1)[0]
    assert "continue-on-error: true" in block
    assert "scripts/mutation_audit.sh" in block
    script = (root / "scripts" / "mutation_audit.sh").read_text(encoding="utf-8")
    for target in (
        "accounting/services.py",
        "core/services/place_of_supply.py",
        "core/services/billing.py",
        "reporting/tds_worksheets.py",
        "inventory/services.py",
    ):
        assert target in script

