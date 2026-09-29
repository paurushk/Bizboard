"""Audit P0 decisions: one outstanding figure, HSN notices, POS mismatch, opening stock."""

from decimal import Decimal

import pytest

from accounting.models import JournalEntry
from ledgers.services import LedgerService
from masters.hsn_catalog import line_gst_decision, seed_starter_hsn_rates
from masters.models import Product
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _money(payload, *keys):
    body = payload
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        body = body["data"]
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        body = body["error"]
    for key in keys:
        if isinstance(body, dict) and key in body:
            return body[key]
    return None


def test_outstanding_uses_documents_until_backfill_ties(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = False
    company.outstanding_basis = company.OutstandingBasis.GL_WHEN_BOOKS
    company.save(update_fields=["accounting_enabled", "outstanding_basis"])
    product = make_product(tenant_a.company, sku="P0-OS")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Owes")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
        invoice_type="NON_GST",
    )
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert completed.status_code == 200, completed.data
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    company.refresh_from_db()
    outstanding = LedgerService.customer_outstanding(company, customer)
    assert outstanding == invoice.grand_total
    assert outstanding > 0
    settings = tenant_a.client.get("/api/v1/accounting/settings/")
    assert settings.status_code == 200
    assert _money(settings.data, "accounting_backfill_needed", "accountingBackfillNeeded") is True


def test_opening_stock_posts_inventory_gl_when_books_are_on(tenant_a):
    from accounting.services import seed_chart_of_accounts

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    product = make_product(tenant_a.company, sku="P0-OPEN")
    resp = tenant_a.client.post(
        "/api/v1/inventory/opening-stock/",
        {"product": product.id, "quantity": "4", "unit_cost": "25.00"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert JournalEntry.objects.filter(
        company=company,
        source_type="STOCK_MOVEMENT",
        purpose="OPENING_STOCK",
    ).exists()


def test_backfill_preview_does_not_post(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="P0-BF")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Preview")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50.00"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    before = JournalEntry.objects.filter(company=company, source_type="SALES_INVOICE").count()
    preview = tenant_a.client.post(
        "/api/v1/accounting/backfill/",
        {"dry_run": True},
        format="json",
    )
    assert preview.status_code == 200, preview.data
    body = preview.data.get("data", preview.data)
    assert int(body.get("would_post") or body.get("wouldPost") or 0) >= 1
    assert JournalEntry.objects.filter(company=company, source_type="SALES_INVOICE").count() == before


def test_hsn_table_does_not_silently_re_rate(tenant_a):
    seed_starter_hsn_rates()
    rice = line_gst_decision("10063000", Decimal("18"), "", None)
    assert rice["apply"] is False
    assert rice["rate"] == Decimal("18")
    from datetime import date

    dear = line_gst_decision("6109", Decimal("12"), "", date(2026, 1, 15), Decimal("3000"))
    assert dear["apply"] is True
    assert dear["rate"] == Decimal("18")
    assert "price > ₹2,500" in dear["notice"]
    cheap = line_gst_decision("6109", Decimal("12"), "", date(2026, 1, 15), Decimal("500"))
    assert cheap["rate"] == Decimal("5")
    assert "price ≤ ₹2,500" in cheap["notice"]
    unset = line_gst_decision("6109", Decimal("12"), "", date(2026, 1, 15), Decimal("0"))
    assert unset["apply"] is False
    assert unset["rate"] == Decimal("12")

    butter = line_gst_decision("0405", Decimal("12"), "", date(2026, 1, 15))
    assert butter["apply"] is True
    assert butter["rate"] == Decimal("5")
    assert "12%→5%" in butter["notice"]
    packed = line_gst_decision("1006", Decimal("18"), "BRANDED_PREPACKED", date(2026, 1, 15))
    assert packed["apply"] is True
    assert packed["rate"] == Decimal("5")

    saved = tenant_a.client.post(
        "/api/v1/products/",
        {"name": "Basmati", "sku": "RICE-P0", "hsn_code": "1006", "gst_rate": "18"},
        format="json",
    )
    assert saved.status_code == 201, saved.data
    body = saved.data.get("data", saved.data)
    assert Decimal(str(body["gst_rate"])) == Decimal("18")
    product = Product.objects.get(pk=body["id"])
    assert product.gst_rate == Decimal("18")
    assert "branded" in str(body.get("gst_rate_notice") or body.get("gstRateNotice") or "").lower()
    butter_saved = tenant_a.client.post(
        "/api/v1/products/",
        {
            "name": "Butter",
            "sku": "BUTTER-P0",
            "hsn_code": "0405",
            "gst_rate": "12",
            "selling_price": "100.00",
        },
        format="json",
    )
    assert butter_saved.status_code == 201, butter_saved.data
    butter_body = butter_saved.data.get("data", butter_saved.data)
    assert Decimal(str(butter_body["gst_rate"])) == Decimal("5")
    assert "12%→5%" in str(butter_body.get("gst_rate_notice") or butter_body.get("gstRateNotice") or "")


def test_pos_mismatch_message_is_human_and_split_tender_posts_both(tenant_a):
    product = make_product(tenant_a.company, sku="P0-POS", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Till")
    mismatch = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "0",
                }],
            },
            "payment": {
                "mode": "CASH",
                "amount": "100.00",
                "expected_total": "896.00",
            },
        },
        format="json",
    )
    assert mismatch.status_code == 409, mismatch.data
    message = str(_money(mismatch.data, "message") or mismatch.data)
    assert "pos_totals_mismatch" not in message.split("Till")[0]
    assert "Till total changed" in message
    code = _money(mismatch.data, "code")
    assert code == "pos_totals_mismatch"

    from payments.models import CustomerReceipt

    before = CustomerReceipt.objects.filter(company=tenant_a.company).count()
    split = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "0",
                }],
            },
            "payment": {"mode": "CASH", "amount": "100.00", "expected_total": "100.00"},
            "payments": [
                {"mode": "CASH", "amount": "40.00"},
                {"mode": "UPI", "amount": "60.00"},
            ],
        },
        format="json",
    )
    assert split.status_code in (200, 201), split.data
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == before + 2


def test_books_switch_refused_until_backfill_ties(tenant_a):
    empty = tenant_a.client.post(
        "/api/v1/accounting/settings/", {"accounting_enabled": True}, format="json",
    )
    assert empty.status_code == 200, empty.data
    tenant_a.company.refresh_from_db()
    tenant_a.company.accounting_enabled = False
    tenant_a.company.save(update_fields=["accounting_enabled"])

    product = make_product(tenant_a.company, sku="P0-SW")
    add_stock(tenant_a, product, "2")
    refused = tenant_a.client.post(
        "/api/v1/accounting/settings/", {"accounting_enabled": True}, format="json",
    )
    assert refused.status_code == 400, refused.data
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.accounting_enabled is False


def test_full_return_credit_note_matches_rounded_invoice(tenant_a):
    """₹590 + 18% is ₹696.20 before round-off and ₹696.00 on the invoice."""
    from sales.models import SalesCreditNote

    product = make_product(tenant_a.company, sku="P0-CN", gst_rate="18")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Round")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "590.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    assert invoice.grand_total == Decimal("696.00")
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "590.00"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    body = ret.data.get("data", ret.data)
    finished = tenant_a.client.post(f"/api/v1/sales/returns/{body['id']}/complete/")
    assert finished.status_code == 200, finished.data
    note = SalesCreditNote.objects.get(sales_invoice=invoice)
    assert note.grand_total == invoice.grand_total
    statement = LedgerService.customer_statement(tenant_a.company, customer)
    credit = next(row for row in statement if row["type"] == "SALES_CREDIT_NOTE")
    assert credit["credit"] == note.grand_total


def test_full_return_with_tcs_still_matches_the_invoice(tenant_a):
    """Round-off is applied after TCS, so the note does not add TCS a second time."""
    from sales.models import SalesCreditNote

    product = make_product(tenant_a.company, sku="P0-TCS", gst_rate="18")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Tcs Round", gstin="29AAAAA0000A1ZY")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "590.00", "gst_rate": "18"}],
        tcs_section="206C(1H)",
        tcs_rate="0.1",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    assert invoice.tcs_amount > 0
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "590.00"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    body = ret.data.get("data", ret.data)
    finished = tenant_a.client.post(f"/api/v1/sales/returns/{body['id']}/complete/")
    assert finished.status_code == 200, finished.data
    note = SalesCreditNote.objects.get(sales_invoice=invoice)
    assert note.grand_total == invoice.grand_total
    assert note.tcs_amount == invoice.tcs_amount


def test_opening_balance_import_posts_when_books_are_on(tenant_a):
    from accounting.services import seed_chart_of_accounts
    from integrations.tally.adapter import _create_opening_sales
    from masters.models import Product, Unit

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    unit = Unit.objects.create(company=company, name="NOS", short_name="NOS", uqc_code="NOS")
    product = Product.objects.create(
        company=company, name="Opening", sku="OPEN-P0", gst_rate="0",
        purchase_price="500", unit=unit,
    )
    customer = make_customer(company, name="Opening AR")
    invoice = _create_opening_sales(company, tenant_a.owner, customer, Decimal("1500.00"), product)
    assert invoice is not None
    journal = JournalEntry.objects.get(
        company=company, source_type="SALES_INVOICE", source_id=invoice.id,
    )
    assert journal.purpose == "OPENING"
    from inventory.models import StockMovement

    assert not StockMovement.objects.filter(company=company, product=product).exists()


def test_one_receipt_allocates_oldest_invoices_first(tenant_a):
    from datetime import date

    from payments.models import PaymentAllocation

    product = make_product(tenant_a.company, sku="P0-OLD", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Oldest")
    first = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "0"}],
    )
    second = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "40.00", "gst_rate": "0"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{first['id']}/complete/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{second['id']}/complete/").status_code == 200
    SalesInvoice.objects.filter(pk=first["id"]).update(due_date=date(2026, 1, 1))
    SalesInvoice.objects.filter(pk=second["id"]).update(due_date=date(2026, 6, 1))
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "120.00", "mode": "CASH", "allocate_oldest": True},
        format="json",
    )
    assert receipt.status_code == 201, receipt.data
    amounts = {
        row.sales_invoice_id: row.amount
        for row in PaymentAllocation.objects.filter(receipt__customer=customer)
    }
    assert amounts[first["id"]] == Decimal("100.00")
    assert amounts[second["id"]] == Decimal("20.00")


def test_backfill_confirm_is_a_job_and_a_second_run_skips(tenant_a):
    from core.models import AuditEvent

    company = tenant_a.company
    product = make_product(company, sku="P0-JOB")
    add_stock(tenant_a, product, "2")
    customer = make_customer(company, name="Job")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "80.00"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    confirm = tenant_a.client.post(
        "/api/v1/accounting/backfill/", {"confirm": True}, format="json",
    )
    assert confirm.status_code == 200, confirm.data
    body = confirm.data.get("data", confirm.data)
    assert body.get("status") == "done"
    company.refresh_from_db()
    assert company.accounting_enabled is True
    assert JournalEntry.objects.filter(company=company, source_type="SALES_INVOICE").exists()
    assert AuditEvent.objects.filter(
        company=company, description="Accounting backfill posted from the owner screen",
    ).exists()
    posted_first = JournalEntry.objects.filter(company=company).count()
    again = tenant_a.client.post(
        "/api/v1/accounting/backfill/", {"confirm": True}, format="json",
    )
    assert again.status_code == 200, again.data
    again_body = again.data.get("data", again.data)
    assert int(again_body.get("posted") or 0) == 0
    assert JournalEntry.objects.filter(company=company).count() == posted_first


def test_backfill_confirm_blocks_a_closed_period_and_a_large_company(tenant_a):
    from datetime import date

    from accounting.models import AccountingPeriod

    company = tenant_a.company
    product = make_product(company, sku="P0-CLOSED")
    add_stock(tenant_a, product, "2")
    customer = make_customer(company, name="Closed")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10.00"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    AccountingPeriod.objects.create(
        company=company,
        name="Closed",
        start_date=date(2020, 4, 1),
        end_date=date(2021, 3, 31),
        status=AccountingPeriod.Status.CLOSED,
    )
    blocked = tenant_a.client.post(
        "/api/v1/accounting/backfill/", {"confirm": True}, format="json",
    )
    assert blocked.status_code == 400, blocked.data
    assert JournalEntry.objects.filter(company=company, source_type="SALES_INVOICE").count() == 0

    AccountingPeriod.objects.filter(company=company).delete()
    import accounting.views as accounting_views

    original = accounting_views.OWNER_BACKFILL_INVOICE_LIMIT
    accounting_views.OWNER_BACKFILL_INVOICE_LIMIT = 0
    try:
        large = tenant_a.client.post(
            "/api/v1/accounting/backfill/", {"confirm": True}, format="json",
        )
    finally:
        accounting_views.OWNER_BACKFILL_INVOICE_LIMIT = original
    assert large.status_code == 400, large.data
    assert "backfill_accounting_postings" in str(large.data)


def test_opening_purchase_import_posts_when_books_are_on(tenant_a):
    from accounting.services import seed_chart_of_accounts
    from integrations.tally.adapter import _create_opening_purchase
    from masters.models import Product, Unit

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    unit = Unit.objects.create(company=company, name="NOS", short_name="NOS", uqc_code="NOS")
    product = Product.objects.create(
        company=company, name="Opening", sku="OPEN-AP", gst_rate="0",
        purchase_price="500", unit=unit,
    )
    from tests.conftest import make_supplier

    supplier = make_supplier(company, name="Opening AP")
    invoice = _create_opening_purchase(company, tenant_a.owner, supplier, Decimal("900.00"), product)
    assert invoice is not None
    journal = JournalEntry.objects.get(
        company=company, source_type="PURCHASE_INVOICE", source_id=invoice.id,
    )
    assert journal.purpose == "OPENING"
    from inventory.models import StockMovement

    assert not StockMovement.objects.filter(company=company, product=product).exists()


def test_ageing_buckets_add_up_to_the_headline(tenant_a):
    from accounting.services import seed_chart_of_accounts
    from payments.dunning import customer_risk_snapshot

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    product = make_product(company, sku="P0-AGE")
    opened = tenant_a.client.post(
        "/api/v1/inventory/opening-stock/",
        {"product": product.id, "quantity": "10", "unit_cost": "80"},
        format="json",
    )
    assert opened.status_code == 201, opened.data
    customer = make_customer(company, name="Ageing")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000.00"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "400.00", "mode": "CASH"},
        format="json",
    )
    assert receipt.status_code == 201, receipt.data
    snap = customer_risk_snapshot(company, customer)
    headline = Decimal(snap["outstanding"])
    buckets = sum((Decimal(value) for value in snap["ageing"].values()), Decimal("0"))
    assert buckets == headline
    assert Decimal(snap["ageing"]["advances_and_other"]) == headline - Decimal(str(done.data["grand_total"]))


def test_collections_remind_is_a_link_not_a_cloud_send(tenant_a):
    from payments.collections_open import open_invoice_rows

    product = make_product(tenant_a.company, sku="P0-WA", gst_rate="0")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, name="Remind", phone="9876543210")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "25.00", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    rows = open_invoice_rows(tenant_a.company)
    assert len(rows) == 1
    assert rows[0]["customer_phone"] == "9876543210"
    assert rows[0]["remind_url"].startswith("https://wa.me/919876543210?text=")
    assert "Reminder:" in rows[0]["remind_message"]


def test_old_promises_are_not_zero_in_broken_maths(tenant_a):
    from datetime import date

    from payments.models import PaymentPromise
    from payments.promise_to_pay import broken_promise_total, create_promise

    customer = make_customer(tenant_a.company, name="Promised")
    old = create_promise(
        company=tenant_a.company,
        customer=customer,
        promised_date=date(2020, 1, 1),
        user=tenant_a.owner,
    )
    assert old.promised_amount is None
    listed = tenant_a.client.get("/api/v1/payments/promises/?all=1")
    assert listed.status_code == 200, listed.data
    rows = listed.data.get("results", listed.data)
    row = next(item for item in rows if item["id"] == old.id)
    assert row["amount_label"] == "amount not recorded"
    assert row["promised_amount"] is None
    assert broken_promise_total(tenant_a.company, as_of=date(2026, 9, 29)) == Decimal("0")
    recorded = create_promise(
        company=tenant_a.company,
        customer=customer,
        promised_date=date(2020, 1, 2),
        promised_amount="80.00",
        user=tenant_a.owner,
    )
    assert PaymentPromise.objects.get(pk=recorded.id).promised_amount == Decimal("80.00")
    assert broken_promise_total(tenant_a.company, as_of=date(2026, 9, 29)) == Decimal("80.00")


def test_invoice_promise_ignores_money_paid_on_another_invoice(tenant_a):
    from datetime import date

    from payments.models import CustomerReceipt
    from payments.promise_to_pay import create_promise, promise_is_broken
    from payments.services import PaymentService

    product = make_product(tenant_a.company, sku="P0-PROM", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Split pay")
    first = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    second = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "40.00", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{first['id']}/complete/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{second['id']}/complete/").status_code == 200
    receipt = PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("100.00"),
        mode="CASH", user=tenant_a.owner,
    )
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=SalesInvoice.objects.get(pk=first["id"]),
        amount=Decimal("60.00"), user=tenant_a.owner,
    )
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=SalesInvoice.objects.get(pk=second["id"]),
        amount=Decimal("40.00"), user=tenant_a.owner,
    )
    promise = create_promise(
        company=tenant_a.company,
        customer=customer,
        invoice=SalesInvoice.objects.get(pk=first["id"]),
        promised_date=date(2020, 1, 1),
        promised_amount="80.00",
        user=tenant_a.owner,
    )
    assert promise_is_broken(promise, as_of=date(2026, 9, 29)) is True
    assert CustomerReceipt.objects.filter(pk=receipt.id).exists()


def test_gstr3b_purchase_tie_follows_the_filing_gstin(tenant_a):
    """A second GSTIN's purchases stay out of the first registration's worksheet."""
    from accounts.models import CompanyGstin
    from reporting.gst_returns import build_gstr1, build_gstr3b
    from reporting.services import ReportService
    from tests.conftest import make_supplier

    company = tenant_a.company
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.registration_type = company.RegistrationType.REGULAR
    company.save()
    karnataka = CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka",
        is_primary=True, is_active=True,
    )
    maharashtra = CompanyGstin.objects.create(
        company=company, gstin="27AAAAA0000A1Z2", state="Maharashtra",
        is_primary=False, is_active=True,
    )
    product = make_product(company, sku="P0-GSTIN", gst_rate="18")
    local = make_supplier(company, name="KA Supplier", state="Karnataka")
    branch = make_supplier(company, name="MH Supplier", state="Maharashtra")
    first = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": local.id,
            "purchase_type": "GST",
            "company_gstin": karnataka.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert first.status_code == 201, first.data
    first_id = first.data.get("id") or first.data["data"]["id"]
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{first_id}/complete/").status_code == 200
    second = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": branch.id,
            "purchase_type": "GST",
            "company_gstin": maharashtra.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "250.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert second.status_code == 201, second.data
    second_id = second.data.get("id") or second.data["data"]["id"]
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{second_id}/complete/")
    assert done.status_code == 200, done.data
    raw_date = done.data.get("invoice_date") or done.data["data"]["invoice_date"]
    day = str(raw_date)[:10]
    period = day[:7]

    whole = ReportService.purchase_register(company, date_from=day, date_to=day)
    assert Decimal(str(whole["totals"]["taxable"])) == Decimal("350.00")

    for stamp, taxable in ((karnataka, "100.00"), (maharashtra, "250.00")):
        g1 = build_gstr1(company, period, company_gstin=stamp)
        g3b = build_gstr3b(company, period, gstr1=g1, company_gstin=stamp)
        tie = g3b["register_tie"]
        assert tie["purchase"] is True, tie
        assert Decimal(tie["purchase_worksheet"]) == Decimal(taxable)
        scoped = ReportService.purchase_register(
            company, date_from=day, date_to=day, company_gstin_id=stamp.id,
        )
        assert Decimal(str(scoped["totals"]["taxable"])) == Decimal(taxable)
