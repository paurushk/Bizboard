"""Remaining pass-condition slices: audit actor, PROTECT, OTP target, cost export, checkout math."""

import pytest
from django.test import override_settings

from core.models import AuditEvent

pytestmark = pytest.mark.django_db


def _event(company, entity_type, entity_id, description):
    return AuditEvent.objects.filter(
        company=company,
        entity_type=entity_type,
        entity_id=str(entity_id),
        description__icontains=description,
    ).latest("id")


def test_sales_debit_note_complete_records_actor_ip_and_status(tenant_a):
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    product = make_product(tenant_a.company, sku="AUD-DN")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Debit")
    invoice = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{invoice['id']}/complete/").status_code == 200
    created = tenant_a.client.post(
        "/api/v1/sales/debit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "40", "gst_rate": "0"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    done = tenant_a.client.post(
        f"/api/v1/sales/debit-notes/{created.data['id']}/complete/",
        {"confirm_additional_debit": True},
        format="json",
        REMOTE_ADDR="203.0.113.20",
    )
    assert done.status_code == 200, done.data
    event = _event(tenant_a.company, "SalesDebitNote", created.data["id"], "sales_debit_note.completed")
    assert event.user_id == tenant_a.owner.id
    assert event.metadata.get("ip") == "203.0.113.20"
    assert event.metadata.get("before", {}).get("status") == "DRAFT"
    assert event.metadata.get("after", {}).get("status") == "COMPLETED"


def test_journal_reverse_records_the_prior_posted_status(tenant_a):
    from django.utils import timezone

    from accounting.models import Account
    from accounting.services import seed_chart_of_accounts

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    cash = Account.objects.get(company=company, code="1100").id
    equity = Account.objects.get(company=company, code="3200").id
    created = tenant_a.client.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": timezone.localdate().isoformat(),
            "narration": "reverse me",
            "lines": [
                {"account": cash, "debit": "25.00", "credit": "0"},
                {"account": equity, "debit": "0", "credit": "25.00"},
            ],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    jid = created.data["id"]
    assert tenant_a.client.post(f"/api/v1/accounting/journals/{jid}/post/").status_code in (200, 202)
    reversed_resp = tenant_a.client.post(
        f"/api/v1/accounting/journals/{jid}/reverse/", REMOTE_ADDR="203.0.113.21",
    )
    assert reversed_resp.status_code == 200, reversed_resp.data
    event = _event(company, "JournalEntry", jid, "journal.reversed")
    assert event.user_id == tenant_a.owner.id
    assert event.metadata.get("before", {}).get("status") == "POSTED"


def test_period_lock_and_reopen_name_the_actor(tenant_a):
    from reporting.gst_periods import reopen_period, soft_close_period

    locked = soft_close_period(tenant_a.company, "2026-04", tenant_a.owner)
    event = _event(tenant_a.company, "GstReturnPeriod", locked.pk, "period.locked")
    assert event.user_id == tenant_a.owner.id
    assert event.metadata.get("before", {}).get("status") == "OPEN"
    opened = reopen_period(tenant_a.company, "2026-04", tenant_a.owner)
    again = _event(tenant_a.company, "GstReturnPeriod", opened.pk, "period.reopened")
    assert again.user_id == tenant_a.owner.id
    assert again.metadata.get("after", {}).get("status") == "OPEN"


def test_payroll_finalise_writes_an_audit_event(tenant_a):
    from decimal import Decimal as D

    from payroll.models import Employee, PayRun, PaySlip
    from payroll.services import complete_pay_run

    emp = Employee.objects.create(
        company=tenant_a.company, name="P", code="E-AUD", salary=D("30000"),
        pf_applicable=False, esi_applicable=False, pt_state="Maharashtra",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    run = PayRun.objects.create(
        company=tenant_a.company, period="2026-06",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    PaySlip.objects.create(
        company=tenant_a.company, pay_run=run, employee=emp,
        gross=D("30000"), net=D("28000"),
    )
    locked = complete_pay_run(run, tenant_a.owner, pay_from_cash=True)
    event = _event(tenant_a.company, "PayRun", locked.pk, "payroll.finalised")
    assert event.user_id == tenant_a.owner.id
    assert event.metadata.get("before", {}).get("status") == "DRAFT"


def test_amended_invoice_uses_the_coverage_event_name(tenant_a):
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    product = make_product(tenant_a.company, sku="AUD-AM")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Amend")
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    amended = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{draft['id']}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": done.data.get("amend_revision", 0),
            "items": [{"product": product.id, "quantity": "1", "unit_price": "90", "gst_rate": "0"}],
        },
        format="json",
        REMOTE_ADDR="203.0.113.22",
    )
    assert amended.status_code == 200, amended.data
    event = _event(tenant_a.company, "SalesInvoice", draft["id"], "sales_invoice.amended")
    assert event.user_id == tenant_a.owner.id
    assert event.metadata.get("amend") is True
    assert "before" in event.metadata and "after" in event.metadata


def test_stock_balance_blocks_a_hard_product_delete(tenant_a):
    from django.db.models.deletion import ProtectedError

    from masters.models import Product
    from tests.conftest import add_stock, make_product

    product = make_product(tenant_a.company, sku="PROT-1")
    add_stock(tenant_a, product, "3")
    with pytest.raises(ProtectedError):
        Product.objects.filter(pk=product.pk).delete()
    assert Product.objects.filter(pk=product.pk).exists()


def test_otp_limit_follows_the_phone_not_the_ip():
    from django.core.cache import cache
    from rest_framework.test import APIClient

    cache.clear()
    client = APIClient()
    phone = "9999901111"
    with override_settings(PLANWAVE_RATE_LIMIT=True):
        last = None
        for i in range(4):
            last = client.post(
                "/api/v1/auth/otp/request/",
                {"phone": phone},
                format="json",
                REMOTE_ADDR=f"198.51.100.{i + 1}",
            )
        assert last.status_code == 429
        other = client.post(
            "/api/v1/auth/otp/request/",
            {"phone": "9999902222"},
            format="json",
            REMOTE_ADDR="198.51.100.40",
        )
        assert other.status_code != 429


def test_catalogue_export_omits_cost_for_sales_staff(tenant_a):
    import csv
    import io

    from tests.conftest import make_product

    # A cost no other number on the page can equal, so the checks cannot pass or fail by chance.
    make_product(tenant_a.company, sku="COST-1", purchase_price="80.37", selling_price="100")
    owner = tenant_a.client.get("/api/v1/plan/catalog/")
    assert owner.status_code == 200
    owner_rows = list(csv.reader(io.StringIO(owner.content.decode())))
    assert "purchase_price" in owner_rows[0]
    assert owner_rows[1][owner_rows[0].index("purchase_price")] == "80.37"

    staff = tenant_a.staff_client.get("/api/v1/plan/catalog/")
    assert staff.status_code == 200
    staff_rows = list(csv.reader(io.StringIO(staff.content.decode())))
    assert "purchase_price" not in staff_rows[0]
    assert "80.37" not in staff.content.decode()
    assert any(row and row[0] == "COST-1" for row in staff_rows)

    from io import BytesIO

    from pypdf import PdfReader

    def _pdf_text(response):
        assert response.status_code == 200 and response.content.startswith(b"%PDF")
        return "".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages)

    # The page content stream is compressed, so a byte search would pass on anything. Read the text.
    owner_text = _pdf_text(tenant_a.client.get("/api/v1/plan/catalog/?layout=pdf"))
    staff_text = _pdf_text(tenant_a.staff_client.get("/api/v1/plan/catalog/?layout=pdf"))
    assert "80.37" in owner_text  # control: the cost is readable in the owner's PDF
    assert "80.37" not in staff_text
    assert "COST-1" in staff_text


def test_checkout_p95_regression_is_fifteen_percent():
    from perf.checkout_bench import exceeds_baseline, p95_ms

    assert p95_ms([10, 20, 30, 40, 200]) == 200
    assert exceeds_baseline(230, 200) is True
    assert exceeds_baseline(220, 200) is False
