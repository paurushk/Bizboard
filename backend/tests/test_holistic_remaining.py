"""Remaining holistic-validation product-truth checks (7.3, 7.8, 7.9b, P5-T2)."""

from decimal import Decimal

import pytest

from ledgers.services import LedgerService
from payments.services import PaymentService
from sales.models import SalesDebitNote, SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)
from tests.test_pdf_and_share import _complete

pytestmark = pytest.mark.django_db


def _unwrap(payload):
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _residual_returned_invoice(tenant):
    data, product = _complete(tenant)
    invoice = SalesInvoice.objects.get(pk=data["id"])
    ret = tenant.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": invoice.customer_id,
            "sales_invoice": invoice.id,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    done = tenant.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.RETURNED
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("0")

    src = invoice.items.get()
    note = SalesDebitNote.objects.create(
        company=invoice.company,
        customer=invoice.customer,
        sales_invoice=invoice,
        note_date=invoice.invoice_date,
        created_by=tenant.owner,
        updated_by=tenant.owner,
    )
    from sales.notes_services import SalesNotesService

    SalesNotesService.set_debit_note_items(
        note,
        [{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("25"), "source_item": src}],
        tenant.owner,
    )
    SalesNotesService.complete_debit_note(note, tenant.owner)
    invoice = SalesInvoice.objects.get(pk=invoice.pk)
    residual = LedgerService.sales_invoice_outstanding(invoice)
    assert residual > 0
    return invoice, residual


def test_public_pay_shows_live_outstanding_after_return(tenant_a):
    invoice, residual = _residual_returned_invoice(tenant_a)
    invoice = SalesInvoice.objects.get(pk=invoice.pk)
    residual = LedgerService.sales_invoice_outstanding(invoice)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=residual,
        sales_invoice=invoice,
        customer=invoice.customer,
        provider="sandbox",
    )
    public = tenant_a.client.get(f"/api/v1/public/pay/{link.token}/")
    assert public.status_code == 200, public.data
    body = _unwrap(public.data)
    assert Decimal(str(body["amount"])) == residual
    assert body.get("invoice_number") == invoice.number


def test_attention_residual_balance_after_return_copy(tenant_a):
    from insights.attention import build_attention_rows, rupees_to_paise

    invoice, residual = _residual_returned_invoice(tenant_a)
    rows = build_attention_rows(tenant_a.company)
    match = [r for r in rows if r.get("code") == "AR_RESIDUAL_AFTER_RETURN"]
    assert match, rows
    assert "residual balance after return" in (match[0].get("title") or "").lower()
    assert match[0]["money_impact_paise"] == rupees_to_paise(residual)
    assert str(invoice.id) in str(match[0].get("action_href") or "")


def test_accounting_backfill_needed_when_docs_exist_without_journals(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    enabled = tenant_a.client.post("/api/v1/accounting/settings/", {"accounting_enabled": True}, format="json")
    assert enabled.status_code == 200, enabled.data
    settings = tenant_a.client.get("/api/v1/accounting/settings/")
    assert settings.status_code == 200, settings.data
    payload = _unwrap(settings.data)
    assert payload.get("accounting_enabled") is True
    assert payload.get("accounting_backfill_needed") is True


def test_historical_invoice_readable_after_period_close(tenant_a):
    from django.utils import timezone
    from accounting.services import seed_chart_of_accounts

    company = tenant_a.company
    company.accounting_enabled = True
    company.gstin = "29AAAAA0000A1ZY"
    company.gstin_verification_status = "VALID"
    company.gstin_verified_at = timezone.now()
    company.save(
        update_fields=["accounting_enabled", "gstin", "gstin_verification_status", "gstin_verified_at"]
    )
    seed_chart_of_accounts(company, tenant_a.owner)
    invoice, residual = _residual_returned_invoice(tenant_a)
    day = invoice.invoice_date
    period = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "Closed window", "start_date": str(day), "end_date": str(day)},
        format="json",
    )
    assert period.status_code in (200, 201), period.data
    body = _unwrap(period.data)
    pid = body["id"]
    closed = tenant_a.client.post(f"/api/v1/accounting/periods/{pid}/close/")
    assert closed.status_code == 200, closed.data

    fetched = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.id}/")
    assert fetched.status_code == 200, fetched.data
    detail = _unwrap(fetched.data)
    assert detail["status"] == SalesInvoice.Status.RETURNED
    assert Decimal(str(detail["grand_total"])) == invoice.grand_total
    assert LedgerService.sales_invoice_outstanding(invoice) == residual

    product = make_product(tenant_a.company, sku="AFTER-CLOSE")
    add_stock(tenant_a, product, "5")
    blocked = create_draft_invoice(
        tenant_a,
        invoice.customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10.00"}],
        invoice_type="NON_GST",
    )
    SalesInvoice.objects.filter(pk=blocked["id"]).update(invoice_date=day)
    complete = tenant_a.client.post(f"/api/v1/sales/invoices/{blocked['id']}/complete/")
    assert complete.status_code in (400, 403, 409, 422)


def _enable_books(tenant, *, gstin: str | None):
    from django.utils import timezone
    from accounting.services import seed_chart_of_accounts

    company = tenant.company
    company.accounting_enabled = True
    if gstin:
        company.gstin = gstin
        company.gstin_verification_status = "VALID"
        company.gstin_verified_at = timezone.now()
        company.save(
            update_fields=[
                "accounting_enabled",
                "gstin",
                "gstin_verification_status",
                "gstin_verified_at",
            ]
        )
    else:
        company.gstin = ""
        company.gstin_verification_status = "UNVERIFIED"
        company.gstin_verified_at = None
        company.save(
            update_fields=[
                "accounting_enabled",
                "gstin",
                "gstin_verification_status",
                "gstin_verified_at",
            ]
        )
    seed_chart_of_accounts(company, tenant.owner)
    return company


def test_period_close_blocked_when_regular_company_has_no_gstin(tenant_a):
    """Skip-wizard REGULAR tenants still default to GST invoices; close must
    not silently succeed without a GSTIN (ARCH-03 / GST health)."""
    from datetime import date

    from accounting.services import BooksHealthService

    _enable_books(tenant_a, gstin=None)
    product = make_product(tenant_a.company, sku="NO-GSTIN")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00"}],
    )
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert blocked.status_code in (400, 403, 422), blocked.data
    assert "GSTIN" in str(blocked.data).upper() or "gstin" in str(blocked.data).lower()
    codes = {a["code"] for a in BooksHealthService.period_close_blockers(tenant_a.company)}
    assert "GSTIN_MISSING_COMPANY" in codes, codes
    day = date.today()
    period = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "No GSTIN", "start_date": str(day), "end_date": str(day)},
        format="json",
    )
    assert period.status_code in (200, 201), period.data
    pid = _unwrap(period.data)["id"]
    closed = tenant_a.client.post(f"/api/v1/accounting/periods/{pid}/close/")
    assert closed.status_code == 400, closed.data
    assert "GSTIN_MISSING_COMPANY" in str(closed.data)


def test_period_close_after_gst_purchase_receipt_return_and_residual_dn(tenant_a):
    """ARCH-03 money loop against GST invoices: inward + SI + partial receipt
    + full return + residual DN must still be closeable once GSTIN/HSN exist."""
    from datetime import date

    _enable_books(tenant_a, gstin="29AAAAA0000A1ZY")
    product = make_product(tenant_a.company, sku="ARCH03", hsn_code="7318")
    supplier = make_supplier(tenant_a.company)
    customer = make_customer(tenant_a.company, state="Karnataka")
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    rec = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "40", "mode": "UPI"},
        format="json",
    )
    assert rec.status_code in (200, 201), rec.data
    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": rec.data["id"], "sales_invoice": invoice.id, "amount": "40"},
        format="json",
    )
    assert alloc.status_code in (200, 201), alloc.data

    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    done = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.RETURNED

    src = invoice.items.get()
    note = SalesDebitNote.objects.create(
        company=invoice.company,
        customer=invoice.customer,
        sales_invoice=invoice,
        note_date=invoice.invoice_date,
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

    day = date.today()
    period = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "ARCH-03 close", "start_date": str(day), "end_date": str(day)},
        format="json",
    )
    assert period.status_code in (200, 201), period.data
    closed = tenant_a.client.post(f"/api/v1/accounting/periods/{_unwrap(period.data)['id']}/close/")
    assert closed.status_code == 200, closed.data
