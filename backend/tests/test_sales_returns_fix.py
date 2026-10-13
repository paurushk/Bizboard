"""Sales Returns fix plan (SRF-05/06/07/10/11): filters, discounts, line-exact lots,
standalone credit-note headroom, returnable-lines endpoint, totals preview, cancel."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from inventory.models import BatchLot, MovementType, StockBalance, StockMovement
from inventory.services import InventoryService
from sales.models import SalesCreditNote, SalesInvoice, SalesItem, SalesReturn
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _complete_invoice(tenant, customer, items, **extra):
    inv = create_draft_invoice(tenant, customer, items, **extra)
    done = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    return inv


def _return(tenant, customer, invoice_id, items, **extra):
    resp = tenant.client.post(
        "/api/v1/sales/returns/",
        {"customer": customer.id, "sales_invoice": invoice_id, "items": items, **extra},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return resp.data


def _complete_return(tenant, return_id):
    return tenant.client.post(f"/api/v1/sales/returns/{return_id}/complete/")


def _opening(tenant, **payload):
    resp = tenant.client.post("/api/v1/inventory/opening-stock/", payload, format="json")
    assert resp.status_code == 201, resp.data
    return resp


def _books(tenant):
    from accounting.services import seed_chart_of_accounts

    tenant.company.accounting_enabled = True
    tenant.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant.company)


# --- SR-01: list filter -----------------------------------------------------


def test_list_filters_by_sales_invoice_snake_and_camel_and_never_leaks(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-F1")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    line = [{"product": product.id, "quantity": "5", "unit_price": "100"}]
    inv_a = _complete_invoice(tenant_a, customer, line)
    inv_b = _complete_invoice(tenant_a, customer, line)
    ret_a = _return(tenant_a, customer, inv_a["id"], [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    ret_b = _return(tenant_a, customer, inv_b["id"], [{"product": product.id, "quantity": "1", "unit_price": "100"}])

    for param in ("sales_invoice", "salesInvoice"):
        resp = tenant_a.client.get(f"/api/v1/sales/returns/?{param}={inv_a['id']}")
        assert resp.status_code == 200
        ids = {row["id"] for row in resp.data["results"]}
        assert ids == {ret_a["id"]}
        assert ret_b["id"] not in ids


def test_list_date_and_text_filters(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-F2")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, name="Zed Filterable")
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    ret = _return(
        tenant_a, customer, inv["id"],
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        reason="wobbly handle",
    )
    today = date.today()
    base = "/api/v1/sales/returns/"
    assert [r["id"] for r in tenant_a.client.get(f"{base}?q=wobbly").data["results"]] == [ret["id"]]
    assert tenant_a.client.get(f"{base}?q=no-such-thing").data["results"] == []
    assert [r["id"] for r in tenant_a.client.get(f"{base}?q=Filterable").data["results"]] == [ret["id"]]
    inside = tenant_a.client.get(f"{base}?date_from={today - timedelta(days=1)}&date_to={today + timedelta(days=1)}")
    assert [r["id"] for r in inside.data["results"]] == [ret["id"]]
    outside = tenant_a.client.get(f"{base}?date_to={today - timedelta(days=30)}")
    assert outside.data["results"] == []


# --- SR-02: discount + source_item -------------------------------------------


def test_return_keeps_line_discount_on_return_and_credit_note(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-D1")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "4", "unit_price": "100", "discount_percent": "15"}],
    )
    src = SalesItem.objects.get(invoice_id=inv["id"])
    ret = _return(
        tenant_a, customer, inv["id"],
        [{"product": product.id, "quantity": "2", "unit_price": "100", "source_item": src.id}],
    )
    assert Decimal(str(ret["items"][0]["discount_percent"])) == Decimal("15")
    done = _complete_return(tenant_a, ret["id"])
    assert done.status_code == 200, done.data
    note = SalesCreditNote.objects.get(sales_return_id=ret["id"])
    note_line = note.items.get()
    assert note_line.discount_percent == Decimal("15")
    assert Decimal(str(note.taxable_total)) == Decimal("170.00")  # 2 x 100 x 0.85


# --- SR-06: line-exact lots ---------------------------------------------------


def _two_batch_invoice(tenant):
    product = make_product(tenant.company, sku="SRF-L1", gst_rate="0", purchase_price="100")
    product.track_batch = True
    product.save()
    expiry = (date.today() + timedelta(days=90)).isoformat()
    _opening(tenant, product=product.id, quantity="3", batch_no="LOT-A", expiry_date=expiry, unit_cost="100")
    _opening(tenant, product=product.id, quantity="3", batch_no="LOT-B", expiry_date=expiry, unit_cost="200")
    lot_a = BatchLot.objects.get(product=product, batch_no="LOT-A")
    lot_b = BatchLot.objects.get(product=product, batch_no="LOT-B")
    customer = make_customer(tenant.company)
    inv = _complete_invoice(
        tenant, customer,
        [
            {"product": product.id, "quantity": "3", "unit_price": "300", "gst_rate": "0", "batch": lot_a.id},
            {"product": product.id, "quantity": "3", "unit_price": "400", "gst_rate": "0", "batch": lot_b.id},
        ],
        invoice_type="NON_GST",
    )
    items = list(SalesItem.objects.filter(invoice_id=inv["id"]).order_by("id"))
    return product, customer, inv, items, lot_a, lot_b


def test_same_product_two_lines_returning_second_line_restores_its_own_lot(tenant_a):
    _books(tenant_a)
    product, customer, inv, items, lot_a, lot_b = _two_batch_invoice(tenant_a)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    ret = _return(
        tenant_a, customer, inv["id"],
        [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0", "source_item": items[1].id}],
    )
    done = _complete_return(tenant_a, ret["id"])
    assert done.status_code == 200, done.data

    move = StockMovement.objects.get(
        product=product, movement_type=MovementType.SALES_RETURN, reference_id=str(ret["id"])
    )
    assert move.batch_id == lot_b.id
    # Cost reversed is the cost booked on *that line's* sale movement.
    sale = StockMovement.objects.get(
        product=product, movement_type=MovementType.SALE, reason=f"SALE_LINE:{items[1].id}"
    )
    assert sale.batch_id == lot_b.id
    assert move.unit_cost == sale.unit_cost
    assert move.reason == sale.reason
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("2")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("0")

    from accounting.models import JournalEntry

    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_RETURN", source_id=ret["id"], purpose="COGS_REVERSE"
    )
    assert sum(line.debit for line in entry.lines.all()) == (sale.unit_cost * 2).quantize(Decimal("0.01"))


def test_two_lines_of_same_product_in_one_return_do_not_double_restore(tenant_a):
    product, customer, inv, items, lot_a, lot_b = _two_batch_invoice(tenant_a)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    ret = _return(
        tenant_a, customer, inv["id"],
        [
            {"product": product.id, "quantity": "3", "unit_price": "300", "gst_rate": "0", "source_item": items[0].id},
            {"product": product.id, "quantity": "3", "unit_price": "400", "gst_rate": "0", "source_item": items[1].id},
        ],
    )
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("3")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("3")
    restored = StockMovement.objects.filter(
        product=product, movement_type=MovementType.SALES_RETURN, reference_id=str(ret["id"])
    )
    assert sorted((m.batch_id, m.quantity) for m in restored) == sorted(
        [(lot_a.id, Decimal("3")), (lot_b.id, Decimal("3"))]
    )


def test_cancel_after_line_exact_return_reverses_that_lot(tenant_a):
    product, customer, inv, items, lot_a, lot_b = _two_batch_invoice(tenant_a)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    ret = _return(
        tenant_a, customer, inv["id"],
        [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0", "source_item": items[1].id}],
    )
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    cancelled = tenant_a.client.post(f"/api/v1/sales/returns/{ret['id']}/cancel/")
    assert cancelled.status_code == 200, cancelled.data
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("0")


# --- SR-05: damaged scrap -----------------------------------------------------


def test_mixed_condition_return_posts_exact_cogs_and_scrap(tenant_a):
    from accounting.models import JournalEntry

    _books(tenant_a)
    sell = make_product(tenant_a.company, sku="SRF-M1", gst_rate="0")
    dmg = make_product(tenant_a.company, sku="SRF-M2", gst_rate="0")
    add_stock(tenant_a, sell, "5", unit_cost="5000")
    add_stock(tenant_a, dmg, "5", unit_cost="100")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(
        tenant_a, customer,
        [
            {"product": sell.id, "quantity": "1", "unit_price": "6000", "gst_rate": "0"},
            {"product": dmg.id, "quantity": "1", "unit_price": "200", "gst_rate": "0"},
        ],
        invoice_type="NON_GST",
    )
    ret = _return(
        tenant_a, customer, inv["id"],
        [
            {"product": sell.id, "quantity": "1", "unit_price": "6000", "gst_rate": "0", "condition": "SELLABLE"},
            {"product": dmg.id, "quantity": "1", "unit_price": "200", "gst_rate": "0", "condition": "DAMAGED"},
        ],
    )
    assert _complete_return(tenant_a, ret["id"]).status_code == 200

    def debit(purpose):
        entry = JournalEntry.objects.get(
            company=tenant_a.company, source_type="SALES_RETURN", source_id=ret["id"], purpose=purpose
        )
        return sum(line.debit for line in entry.lines.all())

    assert debit("COGS_REVERSE") == Decimal("5100.00")
    assert debit("DAMAGED_SCRAP") == Decimal("100.00")  # not 2550
    adj = StockMovement.objects.get(product=dmg, reference_type="sales_return_damaged")
    assert adj.unit_cost == Decimal("100")


# --- SR-03: serializer ----------------------------------------------------------


def test_serializer_credit_note_fields_and_no_n_plus_one(tenant_a, django_assert_max_num_queries):
    product = make_product(tenant_a.company, sku="SRF-S1")
    add_stock(tenant_a, product, "30")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "20", "unit_price": "100"}])
    invoice_number = SalesInvoice.objects.get(pk=inv["id"]).number
    assert invoice_number
    ids = []
    for _ in range(4):
        ret = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "1", "unit_price": "100"}])
        assert _complete_return(tenant_a, ret["id"]).status_code == 200
        ids.append(ret["id"])

    with django_assert_max_num_queries(40):
        resp = tenant_a.client.get("/api/v1/sales/returns/")
    assert resp.status_code == 200
    rows = {row["id"]: row for row in resp.data["results"]}
    for rid in ids:
        assert rows[rid]["sales_invoice_number"] == invoice_number
        note = SalesCreditNote.objects.get(sales_return_id=rid)
        assert rows[rid]["credit_note_id"] == note.id
        assert rows[rid]["credit_note_number"] == note.number


def test_cancelled_return_has_no_credit_note_link(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-S2")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    ret = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "2", "unit_price": "100"}])
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    cancelled = tenant_a.client.post(f"/api/v1/sales/returns/{ret['id']}/cancel/")
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["credit_note_id"] is None
    assert cancelled.data["credit_note_number"] == ""


# --- SRF-06: standalone credit-note headroom ----------------------------------------


def _standalone_credit(tenant, customer, invoice, product, qty):
    cn = tenant.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": str(qty), "unit_price": "100"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = tenant.client.post(
        f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/",
        {"confirm_price_override": True},
        format="json",
    )
    assert done.status_code == 200, done.data
    return done.data


def test_return_beyond_standalone_credit_headroom_fails_early_and_cleanly(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-H1")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    note = _standalone_credit(tenant_a, customer, inv, product, 2)

    ret = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "4", "unit_price": "100"}])
    before_moves = StockMovement.objects.filter(movement_type=MovementType.SALES_RETURN).count()
    before_notes = SalesCreditNote.objects.count()
    resp = _complete_return(tenant_a, ret["id"])
    assert resp.status_code == 400, resp.data
    text = str(resp.data)
    assert note["number"] in text
    assert "only 3" in text
    assert StockMovement.objects.filter(movement_type=MovementType.SALES_RETURN).count() == before_moves
    assert SalesCreditNote.objects.count() == before_notes
    assert SalesReturn.objects.get(pk=ret["id"]).status == SalesReturn.Status.DRAFT


def test_return_within_standalone_credit_headroom_succeeds(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-H2")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    _standalone_credit(tenant_a, customer, inv, product, 2)
    ret = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "3", "unit_price": "100"}])
    assert _complete_return(tenant_a, ret["id"]).status_code == 200


def test_returnable_lines_endpoint_matches_complete_path(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-H3")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "10", "unit_price": "100"}])
    _standalone_credit(tenant_a, customer, inv, product, 2)
    first = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "3", "unit_price": "100"}])
    assert _complete_return(tenant_a, first["id"]).status_code == 200
    # A draft must not reduce headroom.
    _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "1", "unit_price": "100"}])

    resp = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/returnable-lines/")
    assert resp.status_code == 200, resp.data
    row = resp.data[0]
    assert Decimal(str(row["sold"])) == Decimal("10")
    assert Decimal(str(row["returned"])) == Decimal("3")
    assert Decimal(str(row["credited_standalone"])) == Decimal("2")
    assert Decimal(str(row["returnable"])) == Decimal("5")

    over = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "6", "unit_price": "100"}])
    assert _complete_return(tenant_a, over["id"]).status_code == 400
    ok = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    assert _complete_return(tenant_a, ok["id"]).status_code == 200


def test_returnable_lines_requires_same_company(tenant_a, tenant_b):
    product = make_product(tenant_a.company, sku="SRF-H4")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "2", "unit_price": "100"}])
    assert tenant_b.client.get(f"/api/v1/sales/invoices/{inv['id']}/returnable-lines/").status_code == 404


# --- SRF-11: totals preview ------------------------------------------------------------


def test_preview_totals_matches_the_credit_note_and_persists_nothing(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-P1")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "10", "unit_price": "100", "discount_percent": "10"}],
        invoice_discount="50",
        additional_charges="40",
    )
    src = SalesItem.objects.get(invoice_id=inv["id"])
    payload = {
        "customer": customer.id,
        "sales_invoice": inv["id"],
        "items": [{"product": product.id, "quantity": "4", "unit_price": "100", "source_item": src.id}],
    }
    returns_before = SalesReturn.objects.count()
    notes_before = SalesCreditNote.objects.count()
    moves_before = StockMovement.objects.count()
    preview = tenant_a.client.post("/api/v1/sales/returns/preview-totals/", payload, format="json")
    assert preview.status_code == 200, preview.data
    assert SalesReturn.objects.count() == returns_before
    assert SalesCreditNote.objects.count() == notes_before
    assert StockMovement.objects.count() == moves_before

    ret = _return(tenant_a, customer, inv["id"], payload["items"])
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    note = SalesCreditNote.objects.get(sales_return_id=ret["id"])
    assert Decimal(str(preview.data["grand_total"])) == note.grand_total
    assert Decimal(str(preview.data["taxable_total"])) == note.taxable_total


def test_preview_totals_reports_headroom_errors_and_skips_serial_check(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-P2")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "2", "unit_price": "100"}])
    resp = tenant_a.client.post(
        "/api/v1/sales/returns/preview-totals/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "9", "unit_price": "100"}],
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data


# --- SR-03: cancel reverses everything ------------------------------------------------------


def test_cancel_reverses_stock_credit_note_and_invoice_status(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-C1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    ret = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data["status"] == "RETURNED"

    cancelled = tenant_a.client.post(f"/api/v1/sales/returns/{ret['id']}/cancel/")
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["status"] == "CANCELLED"
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data["status"] == "COMPLETED"
    assert SalesCreditNote.objects.get(sales_return_id=ret["id"]).status == SalesCreditNote.Status.CANCELLED
    balance = StockBalance.objects.get(product=product, warehouse=warehouse, batch__isnull=True)
    assert balance.on_hand == Decimal("0")


# --- permissions ------------------------------------------------------------------------------


def test_staff_can_save_draft_but_not_complete_or_cancel(tenant_a):
    from accounts.models import CompanyUser

    CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.staff).update(can_create_sales=True)
    product = make_product(tenant_a.company, sku="SRF-X1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "3", "unit_price": "100"}])
    created = tenant_a.staff_client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant_a.staff_client.post(f"/api/v1/sales/returns/{created.data['id']}/complete/").status_code == 403
    assert tenant_a.client.post(f"/api/v1/sales/returns/{created.data['id']}/complete/").status_code == 200
    assert tenant_a.staff_client.post(f"/api/v1/sales/returns/{created.data['id']}/cancel/").status_code == 403


# --- legacy (untagged) and challan-origin invoices ------------------------------------------------


def _strip_line_tags(product):
    """Make the invoice look like one sold before line tagging."""
    updated = StockMovement.objects.filter(product=product, movement_type=MovementType.SALE).update(reason="")
    assert updated


def test_untagged_older_invoice_still_restores_the_named_lines_lot(tenant_a):
    product, customer, inv, items, lot_a, lot_b = _two_batch_invoice(tenant_a)
    _strip_line_tags(product)
    warehouse = InventoryService.default_warehouse(tenant_a.company)

    first = _return(
        tenant_a, customer, inv["id"],
        [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0", "source_item": items[1].id}],
    )
    assert _complete_return(tenant_a, first["id"]).status_code == 200
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("2")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("0")

    # A later return of the other line, and the rest of the second, advance correctly.
    second = _return(
        tenant_a, customer, inv["id"],
        [
            {"product": product.id, "quantity": "3", "unit_price": "300", "gst_rate": "0", "source_item": items[0].id},
            {"product": product.id, "quantity": "1", "unit_price": "400", "gst_rate": "0", "source_item": items[1].id},
        ],
    )
    assert _complete_return(tenant_a, second["id"]).status_code == 200
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("3")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("3")


def test_cancel_of_an_untagged_invoice_return_reverses_the_same_lot(tenant_a):
    product, customer, inv, items, lot_a, lot_b = _two_batch_invoice(tenant_a)
    _strip_line_tags(product)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    ret = _return(
        tenant_a, customer, inv["id"],
        [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0", "source_item": items[1].id}],
    )
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    moved = StockMovement.objects.get(product=product, movement_type=MovementType.SALES_RETURN, reference_id=str(ret["id"]))
    assert moved.reason.startswith("SALE_MOVE:")
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret['id']}/cancel/").status_code == 200
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("0")


def test_challan_origin_invoice_restores_the_lot_named_on_the_line(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-CH1", gst_rate="0", purchase_price="100")
    product.track_batch = True
    product.save()
    expiry = (date.today() + timedelta(days=90)).isoformat()
    _opening(tenant_a, product=product.id, quantity="3", batch_no="CH-A", expiry_date=expiry, unit_cost="100")
    _opening(tenant_a, product=product.id, quantity="3", batch_no="CH-B", expiry_date=expiry, unit_cost="200")
    lot_a = BatchLot.objects.get(product=product, batch_no="CH-A")
    lot_b = BatchLot.objects.get(product=product, batch_no="CH-B")
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [
                {"product": product.id, "quantity": "3", "unit_price": "300", "gst_rate": "0", "batch": lot_a.id},
                {"product": product.id, "quantity": "3", "unit_price": "400", "gst_rate": "0", "batch": lot_b.id},
            ],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant_a.client.post(f"/api/v1/sales/delivery-challans/{created.data['id']}/complete/").status_code == 200
    converted = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{created.data['id']}/convert/")
    assert converted.status_code == 200, converted.data
    invoice_id = converted.data["id"]
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/complete/")
    assert done.status_code == 200, done.data
    items = list(SalesItem.objects.filter(invoice_id=invoice_id).order_by("id"))
    assert {i.batch_id for i in items} == {lot_a.id, lot_b.id}
    line_b = next(i for i in items if i.batch_id == lot_b.id)

    ret = _return(
        tenant_a, customer, invoice_id,
        [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0", "source_item": line_b.id}],
    )
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("2")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("0")


# --- invoice status follows "nothing left to return" ---------------------------------------------


def test_part_credited_then_fully_returned_invoice_becomes_returned(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-R1")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    _standalone_credit(tenant_a, customer, inv, product, 2)
    ret = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "3", "unit_price": "100"}])
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data["status"] == "RETURNED"
    # And the returnable-lines endpoint agrees that nothing is left.
    rows = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/returnable-lines/").data
    assert Decimal(str(rows[0]["returnable"])) == Decimal("0")


def test_cancelling_one_of_two_returns_reopens_a_fully_returned_invoice(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-R2")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "4", "unit_price": "100"}])
    first = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "2", "unit_price": "100"}])
    second = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "2", "unit_price": "100"}])
    assert _complete_return(tenant_a, first["id"]).status_code == 200
    assert _complete_return(tenant_a, second["id"]).status_code == 200
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data["status"] == "RETURNED"
    assert tenant_a.client.post(f"/api/v1/sales/returns/{second['id']}/cancel/").status_code == 200
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data["status"] == "COMPLETED"
    # The remaining 2 units can be returned again.
    again = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "2", "unit_price": "100"}])
    assert _complete_return(tenant_a, again["id"]).status_code == 200
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data["status"] == "RETURNED"


# --- FIFO cost layers across partial returns ---------------------------------------------------------


def _fifo_two_layer_sale(tenant):
    from inventory.models import InventoryCostLayer
    from tests.conftest import create_draft_purchase, make_supplier

    tenant.company.inventory_valuation_method = "FIFO"
    tenant.company.save(update_fields=["inventory_valuation_method"])
    product = make_product(tenant.company, sku="SRF-FIFO", gst_rate="0", purchase_price="100")
    supplier = make_supplier(tenant.company)
    for cost in ("100", "200"):
        draft = create_draft_purchase(
            tenant, supplier,
            [{"product": product.id, "quantity": "3", "unit_price": cost, "gst_rate": "0"}],
            purchase_type="NON_GST",
        )
        assert tenant.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    customer = make_customer(tenant.company)
    inv = _complete_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "6", "unit_price": "400", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    layers = list(InventoryCostLayer.objects.filter(company=tenant.company, product=product).order_by("id"))
    assert [l.qty_remaining for l in layers] == [Decimal("0"), Decimal("0")]
    return product, customer, inv, layers


def test_second_partial_return_never_pushes_a_cost_layer_above_its_original_quantity(tenant_a):
    product, customer, inv, layers = _fifo_two_layer_sale(tenant_a)

    def qty():
        return [Decimal(str(l.qty_remaining)) for l in type(layers[0]).objects.filter(pk__in=[x.pk for x in layers]).order_by("id")]

    r1 = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0"}])
    assert _complete_return(tenant_a, r1["id"]).status_code == 200
    assert qty() == [Decimal("2"), Decimal("0")]
    r2 = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0"}])
    assert _complete_return(tenant_a, r2["id"]).status_code == 200
    # 4 back in total: the first layer is full (3) and the second holds the rest (1).
    assert qty() == [Decimal("3"), Decimal("1")]
    assert sum(qty()) == Decimal("4")

    # Cancelling the second return empties what it filled, last layer first.
    assert tenant_a.client.post(f"/api/v1/sales/returns/{r2['id']}/cancel/").status_code == 200
    assert qty() == [Decimal("2"), Decimal("0")]


def test_cancelling_a_middle_return_then_returning_again_keeps_every_layer_exact(tenant_a):
    from inventory.models import InventoryCostLayer

    product, customer, inv, layers = _fifo_two_layer_sale(tenant_a)

    def qty():
        rows = InventoryCostLayer.objects.filter(pk__in=[x.pk for x in layers]).order_by("id")
        return [Decimal(str(r.qty_remaining)) for r in rows]

    def make_return(units):
        r = _return(tenant_a, customer, inv["id"], [{"product": product.id, "quantity": units, "unit_price": "400", "gst_rate": "0"}])
        assert _complete_return(tenant_a, r["id"]).status_code == 200
        return r["id"]

    a = make_return("2")
    b = make_return("2")
    assert qty() == [Decimal("3"), Decimal("1")]
    # Cancel the FIRST of the two: it put 2 on layer 1; B's 1+1 must stay where it is.
    assert tenant_a.client.post(f"/api/v1/sales/returns/{a}/cancel/").status_code == 200
    assert qty() == [Decimal("1"), Decimal("1")]
    # A new return must not land on top of B's units.
    c = make_return("2")
    assert qty() == [Decimal("3"), Decimal("1")]
    assert sum(qty()) == Decimal("4")  # B (2) + C (2)
    assert tenant_a.client.post(f"/api/v1/sales/returns/{b}/cancel/").status_code == 200
    assert qty() == [Decimal("2"), Decimal("0")]
    assert tenant_a.client.post(f"/api/v1/sales/returns/{c}/cancel/").status_code == 200
    assert qty() == [Decimal("0"), Decimal("0")]


# --- challan-origin invoices without a batch on the line; cancelling older returns --------------------


def _challan_invoice_without_batches(tenant, tag_challan_moves=True):
    # Post stock when the challan is completed (then the invoice reuses those movements).
    tenant.company.stock_on_delivery_challan = True
    tenant.company.save(update_fields=["stock_on_delivery_challan"])
    product = make_product(tenant.company, sku="SRF-CH2", gst_rate="0", purchase_price="100")
    product.track_batch = True
    product.save()
    _opening(tenant, product=product.id, quantity="3", batch_no="NB-A",
             expiry_date=(date.today() + timedelta(days=60)).isoformat(), unit_cost="100")
    _opening(tenant, product=product.id, quantity="3", batch_no="NB-B",
             expiry_date=(date.today() + timedelta(days=120)).isoformat(), unit_cost="200")
    lot_a = BatchLot.objects.get(product=product, batch_no="NB-A")
    lot_b = BatchLot.objects.get(product=product, batch_no="NB-B")
    customer = make_customer(tenant.company)
    created = tenant.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [
                {"product": product.id, "quantity": "3", "unit_price": "300", "gst_rate": "0"},
                {"product": product.id, "quantity": "3", "unit_price": "400", "gst_rate": "0"},
            ],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant.client.post(f"/api/v1/sales/delivery-challans/{created.data['id']}/complete/").status_code == 200
    if not tag_challan_moves:
        StockMovement.objects.filter(product=product, reference_type="delivery_challan").update(reason="")
    converted = tenant.client.post(f"/api/v1/sales/delivery-challans/{created.data['id']}/convert/")
    assert converted.status_code == 200, converted.data
    assert tenant.client.post(f"/api/v1/sales/invoices/{converted.data['id']}/complete/").status_code == 200
    items = list(SalesItem.objects.filter(invoice_id=converted.data["id"]).order_by("id"))
    # Without a batch on the line, FEFO gave line 1 the earlier lot and line 2 the later one.
    moves = list(StockMovement.objects.filter(product=product, reference_type="delivery_challan").order_by("id"))
    assert [m.batch_id for m in moves] == [lot_a.id, lot_b.id]
    return product, customer, converted.data["id"], items, lot_a, lot_b


@pytest.mark.parametrize("tagged", [True, False])
def test_challan_origin_invoice_without_batches_restores_the_named_lines_lot(tenant_a, tagged):
    product, customer, invoice_id, items, lot_a, lot_b = _challan_invoice_without_batches(tenant_a, tagged)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    ret = _return(
        tenant_a, customer, invoice_id,
        [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0", "source_item": items[1].id}],
    )
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("2")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("0")


def test_cancelling_an_older_return_without_layer_detail_undoes_the_named_lines_layer(tenant_a):
    from inventory.models import InventoryCostLayer
    from tests.conftest import create_draft_purchase, make_supplier

    tenant_a.company.inventory_valuation_method = "FIFO"
    tenant_a.company.save(update_fields=["inventory_valuation_method"])
    product = make_product(tenant_a.company, sku="SRF-OLD", gst_rate="0", purchase_price="100")
    supplier = make_supplier(tenant_a.company)
    for cost in ("100", "200"):
        draft = create_draft_purchase(
            tenant_a, supplier,
            [{"product": product.id, "quantity": "3", "unit_price": cost, "gst_rate": "0"}],
            purchase_type="NON_GST",
        )
        assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(
        tenant_a, customer,
        [
            {"product": product.id, "quantity": "3", "unit_price": "400", "gst_rate": "0"},
            {"product": product.id, "quantity": "3", "unit_price": "400", "gst_rate": "0"},
        ],
        invoice_type="NON_GST",
    )
    items = list(SalesItem.objects.filter(invoice_id=inv["id"]).order_by("id"))
    layers = list(InventoryCostLayer.objects.filter(company=tenant_a.company, product=product).order_by("id"))
    ret = _return(
        tenant_a, customer, inv["id"],
        [{"product": product.id, "quantity": "2", "unit_price": "400", "gst_rate": "0", "source_item": items[1].id}],
    )
    assert _complete_return(tenant_a, ret["id"]).status_code == 200
    rows = lambda: [Decimal(str(l.qty_remaining)) for l in InventoryCostLayer.objects.filter(pk__in=[x.pk for x in layers]).order_by("id")]  # noqa: E731
    assert rows() == [Decimal("0"), Decimal("2")]
    # Make the return look like one from before per-layer detail was recorded.
    StockMovement.objects.filter(movement_type=MovementType.SALES_RETURN, reference_id=str(ret["id"])).update(
        layer_peels=[], reason=""
    )
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret['id']}/cancel/").status_code == 200
    assert rows() == [Decimal("0"), Decimal("0")]


# --- preview limits -------------------------------------------------------------------------------------


def _preview_payload(customer, inv, product, src, lines=1):
    return {
        "customer": customer.id,
        "sales_invoice": inv["id"],
        "items": [
            {"product": product.id, "quantity": "1", "unit_price": "100", "source_item": src.id}
            for _ in range(lines)
        ],
    }


def test_preview_refuses_more_than_200_lines(tenant_a):
    product = make_product(tenant_a.company, sku="SRF-L200")
    add_stock(tenant_a, product, "400")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "300", "unit_price": "100"}])
    src = SalesItem.objects.get(invoice_id=inv["id"])
    resp = tenant_a.client.post(
        "/api/v1/sales/returns/preview-totals/", _preview_payload(customer, inv, product, src, lines=201), format="json"
    )
    assert resp.status_code == 400, resp.data
    assert "200" in str(resp.data)
    ok = tenant_a.client.post(
        "/api/v1/sales/returns/preview-totals/", _preview_payload(customer, inv, product, src, lines=3), format="json"
    )
    assert ok.status_code == 200, ok.data


def test_preview_has_its_own_rate_limit(tenant_a, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "return_preview", "2/min")
    product = make_product(tenant_a.company, sku="SRF-THR")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = _complete_invoice(tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    src = SalesItem.objects.get(invoice_id=inv["id"])
    payload = _preview_payload(customer, inv, product, src)
    codes = [
        tenant_a.client.post("/api/v1/sales/returns/preview-totals/", payload, format="json").status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]
    # Other return endpoints are not throttled by that scope.
    assert tenant_a.client.get("/api/v1/sales/returns/").status_code == 200
