"""Phase 12 + remaining sales/purchase plan coverage."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from payments.models import ChequeStatus, PaymentMode
from payments.services import PaymentService
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_recurring_stop_stage_invoice_default(tenant_a):
    from sales.models import RecurringInvoiceSchedule, SalesInvoice
    from sales.recurring import generate_draft_for_schedule

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="REC-INV")
    sched = RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=timezone.now() - timedelta(minutes=5),
        line_template={"items": [{"product": product.id, "quantity": "1", "unit_price": "100"}]},
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    assert sched.stop_stage == RecurringInvoiceSchedule.StopStage.INVOICE
    run = generate_draft_for_schedule(sched, user=tenant_a.owner)
    assert run.invoice_id
    assert run.sales_order_id is None
    assert SalesInvoice.objects.get(pk=run.invoice_id).status == SalesInvoice.Status.DRAFT


def test_recurring_stop_stage_delivery_challan_stays_draft_no_stock(tenant_a):
    from inventory.models import StockMovement
    from sales.models import DeliveryChallan, RecurringInvoiceSchedule
    from sales.recurring import generate_draft_for_schedule

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="REC-DC")
    add_stock(tenant_a, product, "10")
    sched = RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=timezone.now() - timedelta(minutes=5),
        stop_stage=RecurringInvoiceSchedule.StopStage.DELIVERY_CHALLAN,
        line_template={"items": [{"product": product.id, "quantity": "1", "unit_price": "100"}]},
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    before = StockMovement.objects.filter(company=tenant_a.company, product=product).count()
    run = generate_draft_for_schedule(sched, user=tenant_a.owner)
    assert run.sales_order_id
    assert run.delivery_challan_id
    assert run.invoice_id is None
    dc = DeliveryChallan.objects.get(pk=run.delivery_challan_id)
    assert dc.status == DeliveryChallan.Status.DRAFT
    after = StockMovement.objects.filter(company=tenant_a.company, product=product).count()
    assert after == before


def test_recurring_stop_stage_sales_order_only(tenant_a):
    from sales.models import RecurringInvoiceSchedule, SalesOrder
    from sales.recurring import generate_draft_for_schedule

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="REC-SO")
    sched = RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.WEEKLY,
        next_run_at=timezone.now() - timedelta(minutes=5),
        stop_stage=RecurringInvoiceSchedule.StopStage.SALES_ORDER,
        line_template={"items": [{"product": product.id, "quantity": "2", "unit_price": "50"}]},
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    run = generate_draft_for_schedule(sched, user=tenant_a.owner)
    assert run.sales_order_id
    assert run.delivery_challan_id is None
    assert run.invoice_id is None
    assert SalesOrder.objects.get(pk=run.sales_order_id).status == SalesOrder.Status.DRAFT


def test_day_book_counts_cleared_cheques_only(tenant_a):
    from reporting.transactions import day_book

    customer = make_customer(tenant_a.company)
    rec = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("200.00"),
        mode=PaymentMode.CHEQUE,
        user=tenant_a.owner,
        cheque_number="111111",
        cheque_bank_name="SBI",
    )
    today = timezone.localdate()
    book = day_book(tenant_a.company, today)
    assert all(r.get("id") != rec.id or r["txn_type"] != "PAYMENT_IN" for r in book["rows"])
    PaymentService.set_cheque_status(receipt=rec, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    book2 = day_book(tenant_a.company, today)
    assert any(r.get("id") == rec.id and r["txn_type"] == "PAYMENT_IN" for r in book2["rows"])


def test_ledger_union_is_sales_side_only(tenant_a):
    from reporting.transactions import sales_side_transactions

    customer = make_customer(tenant_a.company, name="Same Name Co")
    supplier = make_supplier(tenant_a.company, name="Same Name Co")
    product = make_product(tenant_a.company, sku="LED-1")
    add_stock(tenant_a, product, "5")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    from tests.conftest import create_draft_purchase

    pur = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "40"}]
    )
    tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    rows = sales_side_transactions(tenant_a.company, customer_id=customer.id)
    kinds = {r["txn_type"] for r in rows}
    assert "SALES" in kinds
    assert "PAYMENT_OUT" not in kinds
    assert all(r["customer_id"] == customer.id for r in rows)


def test_delivery_route_lifecycle(tenant_a):
    from sales.models import SalesOrder

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RT-1")
    order = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "expected_price": "110"}],
            "delivery_address": "Warehouse gate",
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    route = tenant_a.client.post(
        "/api/v1/sales/delivery-routes/",
        {"route_date": timezone.localdate().isoformat(), "vehicle_number": "KA01AB1234"},
        format="json",
    )
    assert route.status_code == 201, route.data
    added = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.data['id']}/add-orders/",
        {"order_ids": [order.data["id"]]},
        format="json",
    )
    assert added.status_code == 200, added.data
    assert added.data["rollup"]["stop_count"] == 1
    stop_id = added.data["stops"][0]["id"]
    start = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.data['id']}/start/")
    assert start.status_code == 200
    remove = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.data['id']}/remove-stop/",
        {"stop_id": stop_id},
        format="json",
    )
    assert remove.status_code == 400
    mark = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.data['id']}/set-stop-status/",
        {"stop_id": stop_id, "status": "FAILED"},
        format="json",
    )
    assert mark.status_code == 200, mark.data
    done = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.data['id']}/complete/")
    assert done.status_code == 200
    assert done.data["status"] == "COMPLETED"
    assert SalesOrder.objects.get(pk=order.data["id"]).delivery_address == "Warehouse gate"


def test_expense_crud(tenant_a):
    from masters.models import ExpenseCategory

    cat = ExpenseCategory.objects.create(company=tenant_a.company, name="Fuel")
    created = tenant_a.client.post(
        "/api/v1/accounting/expenses/",
        {"category": cat.id, "amount": "500.00", "party_name": "HP Pump", "notes": "Diesel"},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["number"]
    listing = tenant_a.client.get("/api/v1/accounting/expenses/")
    assert listing.status_code == 200
    assert listing.data["results"][0]["amount"] == "500.00"
    updated = tenant_a.client.patch(
        f"/api/v1/accounting/expenses/{created.data['id']}/",
        {"notes": "Updated diesel", "party_name": "IOCL"},
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.data["notes"] == "Updated diesel"
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = tenant_a.client.post(
        "/api/v1/files/",
        {"kind": "ATTACHMENT", "file": SimpleUploadedFile("bill.pdf", b"%PDF-1.4 test", content_type="application/pdf")},
        format="multipart",
    )
    assert upload.status_code == 201, upload.data
    attached = tenant_a.client.patch(
        f"/api/v1/accounting/expenses/{created.data['id']}/",
        {"attachment": upload.data["id"]},
        format="json",
    )
    assert attached.status_code == 200, attached.data
    assert attached.data.get("attachment") == upload.data["id"]


def test_expected_profit_uses_purchase_price(tenant_a):
    from sales.expected_profit import expected_profit_for_order
    from sales.models import SalesOrder

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="EP-1", purchase_price="80")
    order = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}]},
        format="json",
    )
    assert order.status_code == 201, order.data
    so = SalesOrder.objects.get(pk=order.data["id"])
    payload = expected_profit_for_order(so)
    assert payload["expected_revenue"] == Decimal("200.00")
    assert payload["expected_cost"] == Decimal("160.00")
    assert payload["expected_profit"] == Decimal("40.00")
    assert payload["label"] == "Expected/Estimated Profit"


def test_expected_profit_applies_line_discount(tenant_a):
    """A discounted line's expected profit must reflect the discounted
    revenue, not the gross pre-discount amount — otherwise a loss-making
    discounted order can show as profitable on the Delivery Route rollup."""
    from sales.expected_profit import expected_profit_for_order
    from sales.models import SalesOrder

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="EP-DISC", purchase_price="80")
    order = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "items": [
                {"product": product.id, "quantity": "10", "unit_price": "100", "discount_percent": "50"}
            ],
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    so = SalesOrder.objects.get(pk=order.data["id"])
    payload = expected_profit_for_order(so)
    # gross 1000, 50% discount -> revenue 500; cost 10*80=800 -> a real loss.
    assert payload["expected_revenue"] == Decimal("500.00")
    assert payload["expected_cost"] == Decimal("800.00")
    assert payload["expected_profit"] == Decimal("-300.00")


def test_invoice_search_by_customer_name(tenant_a):
    customer = make_customer(tenant_a.company, name="UniqueSearchParty")
    product = make_product(tenant_a.company, sku="SRCH-1")
    add_stock(tenant_a, product, "2")
    create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}]
    )
    resp = tenant_a.client.get("/api/v1/sales/invoices/?q=UniqueSearchParty")
    assert resp.status_code == 200
    assert resp.data["count"] >= 1


def _preview_money(payload, *keys):
    for key in keys:
        if key in payload and payload[key] is not None:
            return Decimal(str(payload[key]))
    return Decimal("0")


def test_after_tax_header_discount_does_not_change_taxable(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="DISC-A", gst_rate="18")
    items = [{"product": product.id, "quantity": "1", "unit_price": "1000"}]
    base = tenant_a.client.post(
        "/api/v1/sales/invoices/preview-totals/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "items": items,
            "invoice_discount": "0",
            "invoice_discount_mode": "AFTER_TAX",
            "auto_round_off": False,
        },
        format="json",
    )
    discounted = tenant_a.client.post(
        "/api/v1/sales/invoices/preview-totals/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "items": items,
            "invoice_discount": "180",
            "invoice_discount_mode": "AFTER_TAX",
            "auto_round_off": False,
        },
        format="json",
    )
    assert base.status_code == 200, base.data
    assert discounted.status_code == 200, discounted.data
    assert _preview_money(base.data, "taxable_total", "taxableTotal") == _preview_money(
        discounted.data, "taxable_total", "taxableTotal"
    )
    assert _preview_money(base.data, "tax_total", "taxTotal") == _preview_money(
        discounted.data, "tax_total", "taxTotal"
    )
    assert _preview_money(discounted.data, "grand_total", "grandTotal") == _preview_money(
        base.data, "grand_total", "grandTotal"
    ) - Decimal("180")


def test_preview_totals_walk_in_without_customer(tenant_a):
    product = make_product(tenant_a.company, sku="WALK-PV")
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/preview-totals/",
        {
            "invoice_type": "RETAIL",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
            "auto_round_off": True,
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert _preview_money(resp.data, "grand_total", "grandTotal") > 0


def test_delivery_route_manifest_pdf(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RT-PDF")
    order = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
            "delivery_address": "Gate 2",
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    route = tenant_a.client.post(
        "/api/v1/sales/delivery-routes/",
        {"route_date": timezone.localdate().isoformat(), "vehicle_number": "KA02CD9999"},
        format="json",
    )
    assert route.status_code == 201, route.data
    tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.data['id']}/add-orders/",
        {"order_ids": [order.data["id"]]},
        format="json",
    )
    pdf = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.data['id']}/manifest/")
    assert pdf.status_code == 200
    content = b"".join(pdf.streaming_content)
    assert content.startswith(b"%PDF")
    from io import BytesIO

    from pypdf import PdfReader

    text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(content)).pages)
    assert "MANIFEST" in text
    assert "KA02CD9999" in text or "Gate 2" in text


def test_delivery_challan_return_restocks_when_stock_posted(tenant_a):
    from inventory.models import InventoryCostLayer, StockBalance

    tenant_a.company.stock_on_delivery_challan = True
    tenant_a.company.inventory_valuation_method = "FIFO"
    tenant_a.company.save(update_fields=["stock_on_delivery_challan", "inventory_valuation_method"])
    product = make_product(tenant_a.company, sku="DC-RET", gst_rate="0")
    add_stock(tenant_a, product, "10", unit_cost="80")
    customer = make_customer(tenant_a.company)
    challan = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "4", "unit_price": "50", "gst_rate": "0"}],
        },
        format="json",
    )
    assert challan.status_code == 201, challan.data
    done = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan.data['id']}/complete/")
    assert done.status_code == 200, done.data
    after_dispatch = StockBalance.objects.get(company=tenant_a.company, product=product).on_hand
    ret = tenant_a.client.post(
        "/api/v1/sales/challan-returns/",
        {
            "customer": customer.id,
            "challan": challan.data["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "50", "gst_rate": "0"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    completed = tenant_a.client.post(f"/api/v1/sales/challan-returns/{ret.data['id']}/complete/")
    assert completed.status_code == 200, completed.data
    after_return = StockBalance.objects.get(company=tenant_a.company, product=product).on_hand
    assert after_return == after_dispatch + Decimal("2")

    # FIFO must restore the returned quantity onto the *original* ₹80 cost
    # layer (restore_fifo_peels puts peeled qty back on the original layer by
    # design — it does not mint a fresh layer) so future COGS still consumes
    # at the real historical cost, not an invented/zero one. 10 opening stock
    # - 4 dispatched + 2 returned = 8 remaining on that one layer.
    layer = InventoryCostLayer.objects.get(company=tenant_a.company, product=product)
    assert layer.unit_cost == Decimal("80.0000")
    assert layer.qty_remaining == Decimal("8.000")


def test_customer_ledger_xlsx_export(tenant_a):
    customer = make_customer(tenant_a.company, name="Ledger Excel Co")
    product = make_product(tenant_a.company, sku="LX-1")
    add_stock(tenant_a, product, "2")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    resp = tenant_a.client.get(f"/api/v1/reports/customer-ledger/{customer.id}/?export=xlsx")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp["Content-Type"]
    assert resp.content[:2] == b"PK"


def test_customer_list_sort_recent(tenant_a):
    from masters.models import Customer

    first = make_customer(tenant_a.company, name="Alpha Sort")
    second = make_customer(tenant_a.company, name="Zed Sort")
    Customer.objects.filter(pk=first.pk).update(updated_at=timezone.now() - timedelta(days=3))
    by_name = tenant_a.client.get("/api/v1/customers/?sort=name")
    assert by_name.status_code == 200
    names = [row["name"] for row in by_name.data["results"] if row["name"] in ("Alpha Sort", "Zed Sort")]
    assert names == ["Alpha Sort", "Zed Sort"]
    recent = tenant_a.client.get("/api/v1/customers/?sort=recent")
    assert recent.status_code == 200
    recent_names = [row["name"] for row in recent.data["results"] if row["name"] in ("Alpha Sort", "Zed Sort")]
    assert recent_names[0] == "Zed Sort"


def test_quotation_expected_profit_on_retrieve(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="QEP-1", purchase_price="40")
    quote = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}]},
        format="json",
    )
    assert quote.status_code == 201, quote.data
    profit = quote.data.get("expected_profit") or quote.data.get("expectedProfit") or {}
    assert Decimal(str(profit.get("expected_profit") or profit.get("expectedProfit"))) == Decimal("120.00")


def test_sales_summary_includes_payment_breakdown(tenant_a):
    resp = tenant_a.client.get("/api/v1/reports/sales-summary/")
    assert resp.status_code == 200
    payload = resp.data.get("payment_breakdown") or resp.data.get("paymentBreakdown")
    assert payload is not None
    assert "paid" in payload or "unpaid" in payload
    by_date = resp.data.get("by_date")
    if by_date is None:
        by_date = resp.data.get("byDate")
    assert by_date is not None
    assert isinstance(by_date, list)


def _ledger_kpi(payload, *keys):
    kpis = payload.get("kpis") or {}
    for key in keys:
        if key in kpis and kpis[key] is not None:
            return Decimal(str(kpis[key]))
    return Decimal("0")


def test_customer_ledger_status_filter_and_overdue_kpi(tenant_a):
    from sales.models import SalesInvoice

    customer = make_customer(tenant_a.company, name="Ledger Status Co")
    product = make_product(tenant_a.company, sku="LS-1")
    add_stock(tenant_a, product, "10")
    overdue_inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    current_inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "80"}]
    )
    paid_inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "60"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{overdue_inv['id']}/complete/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{current_inv['id']}/complete/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{paid_inv['id']}/complete/").status_code == 200
    today = timezone.localdate()
    SalesInvoice.objects.filter(pk=overdue_inv["id"]).update(
        invoice_date=today - timedelta(days=40),
        due_date=today - timedelta(days=10),
    )
    SalesInvoice.objects.filter(pk=current_inv["id"]).update(due_date=today + timedelta(days=30))
    SalesInvoice.objects.filter(pk=paid_inv["id"]).update(due_date=today + timedelta(days=15))

    paid_obj = SalesInvoice.objects.get(pk=paid_inv["id"])
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=paid_obj.grand_total,
        mode=PaymentMode.CASH,
        user=tenant_a.owner,
    )
    PaymentService.allocate_receipt(
        receipt=receipt,
        sales_invoice=paid_obj,
        amount=paid_obj.grand_total,
        user=tenant_a.owner,
    )

    unpaid = tenant_a.client.get(f"/api/v1/reports/customer-ledger/{customer.id}/?status=UNPAID")
    assert unpaid.status_code == 200, unpaid.data
    unpaid_ids = {
        row.get("id")
        for row in (unpaid.data.get("transactions") or [])
        if (row.get("txn_type") or row.get("txnType")) == "SALES"
    }
    assert overdue_inv["id"] in unpaid_ids
    assert current_inv["id"] in unpaid_ids
    assert paid_inv["id"] not in unpaid_ids

    paid = tenant_a.client.get(f"/api/v1/reports/customer-ledger/{customer.id}/?status=PAID")
    assert paid.status_code == 200, paid.data
    paid_ids = {
        row.get("id")
        for row in (paid.data.get("transactions") or [])
        if (row.get("txn_type") or row.get("txnType")) == "SALES"
    }
    assert paid_inv["id"] in paid_ids
    assert overdue_inv["id"] not in paid_ids
    assert current_inv["id"] not in paid_ids

    overdue_rows = tenant_a.client.get(f"/api/v1/reports/customer-ledger/{customer.id}/?status=OVERDUE")
    assert overdue_rows.status_code == 200
    overdue_ids = {
        row.get("id")
        for row in (overdue_rows.data.get("transactions") or [])
        if (row.get("txn_type") or row.get("txnType")) == "SALES"
    }
    assert overdue_inv["id"] in overdue_ids
    assert current_inv["id"] not in overdue_ids

    all_tabs = tenant_a.client.get(f"/api/v1/reports/customer-ledger/{customer.id}/")
    assert all_tabs.status_code == 200
    outstanding = _ledger_kpi(all_tabs.data, "total_receivable", "totalReceivable")
    overdue_amt = _ledger_kpi(all_tabs.data, "overdue_amount", "overdueAmount")
    assert overdue_amt > 0
    assert outstanding > overdue_amt

    statement = all_tabs.data.get("statement")
    entries = statement.get("entries") if isinstance(statement, dict) else statement
    assert entries
    first = entries[0]
    assert first.get("sr_no") == 1 or first.get("srNo") == 1
    receipt_row = next(
        row for row in entries if str(row.get("type") or "").upper() in ("RECEIPT", "CUSTOMER_RECEIPT")
    )
    assert str(receipt_row.get("mode") or "").upper() == "CASH"


def test_quotation_convert_chain_quote_to_invoice(tenant_a):
    customer = make_customer(tenant_a.company, shipping_address="Yard 4")
    product = make_product(tenant_a.company, sku="CHAIN-1")
    add_stock(tenant_a, product, "5")
    quote = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": customer.id,
            "sales_channel": "WALK_IN",
            "delivery_address": "Gate 2, Peenya",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "expected_price": "110"}],
        },
        format="json",
    )
    assert quote.status_code == 201, quote.data
    assert (quote.data.get("sales_channel") or quote.data.get("salesChannel")) == "WALK_IN"
    assert (quote.data.get("delivery_address") or quote.data.get("deliveryAddress")) == "Gate 2, Peenya"
    chain = tenant_a.client.post(
        f"/api/v1/sales/quotations/{quote.data['id']}/convert-chain/",
        {"stop_stage": "INVOICE"},
        format="json",
    )
    assert chain.status_code == 200, chain.data
    order = chain.data.get("sales_order") or chain.data.get("salesOrder")
    challan = chain.data.get("delivery_challan") or chain.data.get("deliveryChallan")
    invoice = chain.data.get("invoice")
    assert order and challan and invoice
    assert (challan.get("status") or "").upper() == "COMPLETED"
    assert (invoice.get("status") or "").upper() == "DRAFT"


def test_record_payment_settlement_discount_does_not_change_gst(tenant_a):
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="SETL-1", gst_rate="18")
    add_stock(tenant_a, product, "2")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "1000"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    obj = SalesInvoice.objects.get(pk=inv["id"])
    taxable_before = obj.taxable_total
    cgst_before = obj.cgst_total
    paid = tenant_a.client.post(
        f"/api/v1/sales/invoices/{obj.id}/record-payment/",
        {"amount": "100.00", "discount": "50.00", "mode": "CASH"},
        format="json",
    )
    assert paid.status_code == 200, paid.data
    obj.refresh_from_db()
    assert obj.taxable_total == taxable_before
    assert obj.cgst_total == cgst_before
    outstanding = LedgerService.sales_invoice_outstanding(obj)
    assert outstanding == obj.grand_total - Decimal("150.00")


def test_settlement_discount_prorated_across_split_receipt_not_double_counted(tenant_a):
    """A single receipt's settlement_discount must be prorated across the
    invoices it's split-allocated to, in both the single-invoice and the
    bulk outstanding calculation — charging the full discount against every
    invoice the receipt touches would understate total AR."""
    from ledgers.services import LedgerService
    from payments.models import CustomerReceipt, PaymentAllocation, ReceiptStatus
    from sales.models import SalesInvoice

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="SETL-SPLIT", gst_rate="0")
    add_stock(tenant_a, product, "4")
    inv_a = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "1000"}]
    )
    inv_b = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "1000"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv_a['id']}/complete/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv_b['id']}/complete/").status_code == 200
    obj_a = SalesInvoice.objects.get(pk=inv_a["id"])
    obj_b = SalesInvoice.objects.get(pk=inv_b["id"])

    # One receipt for 1800, with a 100 settlement discount, split evenly (900/900)
    # across the two 1000 invoices. Each invoice's *correct* share of the
    # discount is 50 (prorated by its share of the receipt), leaving 50
    # outstanding per invoice (1000 - 900 - 50). The bug this guards against
    # would apply the full 100 to each invoice instead of prorating —
    # 1000 - 900 - 100 = 0 — so 50 vs. 0 is the distinguishing assertion.
    receipt = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("1800.00"),
        settlement_discount=Decimal("100.00"),
        receipt_date=obj_a.invoice_date,
        status=ReceiptStatus.POSTED,
        mode="CASH",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company, receipt=receipt, sales_invoice=obj_a, amount=Decimal("900.00")
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company, receipt=receipt, sales_invoice=obj_b, amount=Decimal("900.00")
    )

    single_a = LedgerService.sales_invoice_outstanding(obj_a)
    single_b = LedgerService.sales_invoice_outstanding(obj_b)
    assert single_a == Decimal("50.00")
    assert single_b == Decimal("50.00")

    bulk = LedgerService.bulk_sales_invoice_outstanding(tenant_a.company, [obj_a.id, obj_b.id])
    assert bulk[obj_a.id] == Decimal("50.00")
    assert bulk[obj_b.id] == Decimal("50.00")


def test_bulk_pdf_zip_returns_download_url_and_caps_at_100(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="ZIP-1")
    add_stock(tenant_a, product, "2")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    zipped = tenant_a.client.post(
        "/api/v1/sales/invoices/bulk-pdf-zip/",
        {"ids": [inv["id"]]},
        format="json",
    )
    assert zipped.status_code == 200, zipped.data
    assert zipped.data.get("url")
    assert zipped.data.get("file_id") or zipped.data.get("fileId")
    capped = tenant_a.client.post(
        "/api/v1/sales/invoices/bulk-pdf-zip/",
        {"ids": list(range(1, 102))},
        format="json",
    )
    assert capped.status_code == 400


def test_invoice_hsn_summary_and_payment_stats(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="HSN-SUM", hsn_code="998811", gst_rate="18")
    add_stock(tenant_a, product, "2")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    summary = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/hsn-summary/")
    assert summary.status_code == 200, summary.data
    rows = summary.data.get("rows") or []
    assert rows
    stats = tenant_a.client.get("/api/v1/sales/invoices/payment-stats/")
    assert stats.status_code == 200, stats.data
    unpaid = stats.data.get("unpaid") or {}
    assert int(unpaid.get("count") or 0) >= 1


def test_purchase_ship_from_is_printed_on_pdf(tenant_a):
    from io import BytesIO

    from pypdf import PdfReader

    from purchases.models import PurchaseInvoice
    from purchases.pdf import render_gst_purchase_bill

    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="SHIP-1")
    created = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "ship_from": "Factory Gate",
            "ship_from_address": "Plot 12, Peenya",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "40"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{created.data['id']}/complete/").status_code == 200
    invoice = PurchaseInvoice.objects.select_related("supplier", "company").prefetch_related("items__product").get(
        pk=created.data["id"]
    )
    content = render_gst_purchase_bill(invoice)
    text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(content)).pages)
    assert "SHIP FROM" in text
    assert "Factory Gate" in text
