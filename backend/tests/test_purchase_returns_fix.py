"""Purchase Returns parity with Sales Returns: server headroom, standalone credit
notes, returned serials, filters, serializer links and the draft lifecycle."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from inventory.models import SerialNumber
from purchases.models import PurchaseCreditNote, PurchaseItem, PurchaseReturn
from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _purchase(tenant, supplier, product, qty="5", price="100", **extra):
    draft = create_draft_purchase(
        tenant, supplier,
        [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": "0", **extra}],
        purchase_type="NON_GST",
    )
    done = tenant.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    return draft["id"], PurchaseItem.objects.get(invoice_id=draft["id"])


def _return(tenant, supplier, invoice_id, qty, reason="", **line):
    resp = tenant.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": invoice_id,
            "reason": reason,
            "items": [{"product": line.pop("product"), "quantity": qty, "unit_price": "100", "gst_rate": "0", **line}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return resp.data["id"]


def _complete(tenant, return_id):
    return tenant.client.post(f"/api/v1/purchases/returns/{return_id}/complete/")


def _standalone_credit(tenant, supplier, invoice_id, src, qty):
    cn = tenant.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": invoice_id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{
                "product": src.product_id, "quantity": str(qty), "unit_price": "100",
                "gst_rate": "0", "source_item": src.id,
            }],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = tenant.client.post(
        f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/", {"confirm_price_override": True}, format="json"
    )
    assert done.status_code == 200, done.data
    return done.data


def test_returnable_lines_counts_returns_and_standalone_credit_notes(tenant_a):
    product = make_product(tenant_a.company, sku="PRF-1", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    invoice_id, src = _purchase(tenant_a, supplier, product, qty="10")
    _standalone_credit(tenant_a, supplier, invoice_id, src, 2)
    first = _return(tenant_a, supplier, invoice_id, "3", product=product.id)
    assert _complete(tenant_a, first).status_code == 200
    _return(tenant_a, supplier, invoice_id, "1", product=product.id)  # a draft must not count

    rows = tenant_a.client.get(f"/api/v1/purchases/invoices/{invoice_id}/returnable-lines/")
    assert rows.status_code == 200, rows.data
    row = rows.data[0]
    assert row["source_item"] == src.id
    assert Decimal(str(row["purchased"])) == Decimal("10")
    assert Decimal(str(row["returned"])) == Decimal("3")
    assert Decimal(str(row["credited_standalone"])) == Decimal("2")
    assert Decimal(str(row["returnable"])) == Decimal("5")

    too_many = _return(tenant_a, supplier, invoice_id, "6", product=product.id)
    assert _complete(tenant_a, too_many).status_code == 400
    ok = _return(tenant_a, supplier, invoice_id, "5", product=product.id)
    assert _complete(tenant_a, ok).status_code == 200


def test_return_past_standalone_credit_headroom_is_refused_without_side_effects(tenant_a):
    product = make_product(tenant_a.company, sku="PRF-2", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    invoice_id, src = _purchase(tenant_a, supplier, product, qty="5")
    _standalone_credit(tenant_a, supplier, invoice_id, src, 2)
    ret = _return(tenant_a, supplier, invoice_id, "4", product=product.id)
    notes_before = PurchaseCreditNote.objects.count()
    resp = _complete(tenant_a, ret)
    assert resp.status_code == 400, resp.data
    assert "remaining returnable quantity 3" in str(resp.data)
    assert PurchaseCreditNote.objects.count() == notes_before
    assert PurchaseReturn.objects.get(pk=ret).status == PurchaseReturn.Status.DRAFT


def test_returnable_lines_lists_returned_serials_and_hides_nothing_else(tenant_a):
    product = make_product(tenant_a.company, sku="PRF-3", gst_rate="0", track_serial=True)
    supplier = make_supplier(tenant_a.company)
    invoice_id, _src = _purchase(
        tenant_a, supplier, product, qty="3", serial_numbers=["PS-1", "PS-2", "PS-3"]
    )
    ret = _return(tenant_a, supplier, invoice_id, "1", product=product.id, serial_numbers=["PS-2"])
    assert _complete(tenant_a, ret).status_code == 200
    rows = tenant_a.client.get(f"/api/v1/purchases/invoices/{invoice_id}/returnable-lines/").data
    assert rows[0]["returned_serials"] == ["PS-2"]
    assert Decimal(str(rows[0]["returnable"])) == Decimal("2")
    assert SerialNumber.objects.filter(company=tenant_a.company, serial_number="PS-2").exists()


def test_purchase_return_serializer_links_and_filters(tenant_a):
    product = make_product(tenant_a.company, sku="PRF-4", gst_rate="0")
    supplier = make_supplier(tenant_a.company, name="Zeta Filterable Supplies")
    invoice_id, _src = _purchase(tenant_a, supplier, product, qty="6")
    ret = _return(tenant_a, supplier, invoice_id, "2", product=product.id, reason="cracked casing")
    done = _complete(tenant_a, ret)
    assert done.status_code == 200, done.data
    assert done.data["purchase_invoice_number"]
    note = PurchaseCreditNote.objects.get(purchase_return_id=ret)
    assert done.data["credit_note_id"] == note.id
    assert done.data["credit_note_number"] == note.number

    base = "/api/v1/purchases/returns/"
    today = date.today()
    assert [r["id"] for r in tenant_a.client.get(f"{base}?q=cracked").data["results"]] == [ret]
    assert [r["id"] for r in tenant_a.client.get(f"{base}?q=Filterable").data["results"]] == [ret]
    assert tenant_a.client.get(f"{base}?q=nothing-matches").data["results"] == []
    assert [r["id"] for r in tenant_a.client.get(
        f"{base}?date_from={today - timedelta(days=1)}&date_to={today + timedelta(days=1)}"
    ).data["results"]] == [ret]
    assert tenant_a.client.get(f"{base}?date_to={today - timedelta(days=30)}").data["results"] == []

    cancelled = tenant_a.client.post(f"{base}{ret}/cancel/")
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["credit_note_id"] is None
    assert cancelled.data["credit_note_number"] == ""


def test_returnable_lines_is_tenant_scoped(tenant_a, tenant_b):
    product = make_product(tenant_a.company, sku="PRF-5", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    invoice_id, _src = _purchase(tenant_a, supplier, product, qty="2")
    assert tenant_b.client.get(f"/api/v1/purchases/invoices/{invoice_id}/returnable-lines/").status_code == 404


def test_draft_return_can_be_resumed_updated_and_deleted_but_not_after_completion(tenant_a):
    product = make_product(tenant_a.company, sku="PRF-6", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    invoice_id, _src = _purchase(tenant_a, supplier, product, qty="4")
    ret = _return(tenant_a, supplier, invoice_id, "1", product=product.id)
    patched = tenant_a.client.patch(
        f"/api/v1/purchases/returns/{ret}/",
        {"reason": "changed", "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}]},
        format="json",
    )
    assert patched.status_code == 200, patched.data
    assert tenant_a.client.delete(f"/api/v1/purchases/returns/{ret}/").status_code in (200, 204)
    ret2 = _return(tenant_a, supplier, invoice_id, "1", product=product.id)
    assert _complete(tenant_a, ret2).status_code == 200
    assert tenant_a.client.delete(f"/api/v1/purchases/returns/{ret2}/").status_code == 400


def test_mixed_units_headroom_is_computed_in_base_units_and_reported_in_the_line_unit(tenant_a):
    """A BOX line is stock-counted in pieces, so the endpoint reports in the line's unit."""
    from masters.models import Unit

    product = make_product(tenant_a.company, sku="PRF-7", gst_rate="0")
    box = Unit.objects.create(company=tenant_a.company, name="Box", short_name="BOX", uqc_code="BOX")
    product.alternate_unit = box
    product.conversion_rate = Decimal("10")
    product.save(update_fields=["alternate_unit", "conversion_rate"])
    supplier = make_supplier(tenant_a.company)
    invoice_id, _src = _purchase(tenant_a, supplier, product, qty="2", price="100", unit_name="BOX")

    before = tenant_a.client.get(f"/api/v1/purchases/invoices/{invoice_id}/returnable-lines/").data[0]
    assert Decimal(str(before["purchased"])) == Decimal("2")
    assert Decimal(str(before["returnable"])) == Decimal("2")

    # Return one box (10 pieces): one box is left.
    ret = _return(tenant_a, supplier, invoice_id, "1", product=product.id, unit_name="BOX")
    assert _complete(tenant_a, ret).status_code == 200
    after = tenant_a.client.get(f"/api/v1/purchases/invoices/{invoice_id}/returnable-lines/").data[0]
    assert Decimal(str(after["returned"])) == Decimal("1")
    assert Decimal(str(after["returnable"])) == Decimal("1")


# --- status, cost and layers (audit of the purchase side against the sales fixes) ---------------------


def _invoice_status(tenant, invoice_id):
    return tenant.client.get(f"/api/v1/purchases/invoices/{invoice_id}/").data["status"]


def test_part_credited_then_fully_returned_bill_becomes_returned(tenant_a):
    product = make_product(tenant_a.company, sku="PRA-1", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    invoice_id, src = _purchase(tenant_a, supplier, product, qty="5")
    _standalone_credit(tenant_a, supplier, invoice_id, src, 2)
    ret = _return(tenant_a, supplier, invoice_id, "3", product=product.id)
    assert _complete(tenant_a, ret).status_code == 200
    assert _invoice_status(tenant_a, invoice_id) == "RETURNED"
    rows = tenant_a.client.get(f"/api/v1/purchases/invoices/{invoice_id}/returnable-lines/").data
    assert Decimal(str(rows[0]["returnable"])) == Decimal("0")


def test_cancelling_one_of_two_returns_reopens_a_fully_returned_bill(tenant_a):
    product = make_product(tenant_a.company, sku="PRA-2", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    invoice_id, _src = _purchase(tenant_a, supplier, product, qty="4")
    first = _return(tenant_a, supplier, invoice_id, "2", product=product.id)
    second = _return(tenant_a, supplier, invoice_id, "2", product=product.id)
    assert _complete(tenant_a, first).status_code == 200
    assert _complete(tenant_a, second).status_code == 200
    assert _invoice_status(tenant_a, invoice_id) == "RETURNED"
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{second}/cancel/").status_code == 200
    assert _invoice_status(tenant_a, invoice_id) == "COMPLETED"
    again = _return(tenant_a, supplier, invoice_id, "2", product=product.id)
    assert _complete(tenant_a, again).status_code == 200
    assert _invoice_status(tenant_a, invoice_id) == "RETURNED"


def test_return_cost_is_the_cost_of_the_lot_being_returned(tenant_a):
    from inventory.models import BatchLot, MovementType, StockMovement

    product = make_product(tenant_a.company, sku="PRA-3", gst_rate="0", track_batch=True)
    supplier = make_supplier(tenant_a.company)
    exp = (date.today() + timedelta(days=90)).isoformat()
    draft = create_draft_purchase(
        tenant_a, supplier,
        [
            {"product": product.id, "quantity": "3", "unit_price": "100", "gst_rate": "0", "batch_no": "CA", "exp_date": exp},
            {"product": product.id, "quantity": "3", "unit_price": "200", "gst_rate": "0", "batch_no": "CB", "exp_date": exp},
        ],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    lot_b = BatchLot.objects.get(product=product, batch_no="CB")
    ret = _return(tenant_a, supplier, draft["id"], "2", product=product.id, batch=lot_b.id)
    assert _complete(tenant_a, ret).status_code == 200
    move = StockMovement.objects.get(
        product=product, movement_type=MovementType.PURCHASE_RETURN, reference_id=str(ret)
    )
    assert move.batch_id == lot_b.id
    assert Decimal(str(move.unit_cost)) == Decimal("200")  # not the first receipt's 100


def test_discount_remainder_on_the_closing_return_counts_standalone_credit_notes(tenant_a):
    product = make_product(tenant_a.company, sku="PRA-4", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "NON_GST",
            "invoice_discount": "40",
            "items": [{"product": product.id, "quantity": "4", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    draft = created.data
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    src = PurchaseItem.objects.get(invoice_id=draft["id"])
    standalone = _standalone_credit(tenant_a, supplier, draft["id"], src, 1)
    first = _return(tenant_a, supplier, draft["id"], "1", product=product.id)
    assert _complete(tenant_a, first).status_code == 200
    closing = _return(tenant_a, supplier, draft["id"], "2", product=product.id)
    assert _complete(tenant_a, closing).status_code == 200
    # The bill's discount (40) may be relieved once in total across every credit note.
    notes = PurchaseCreditNote.objects.filter(purchase_invoice_id=draft["id"], status="COMPLETED")
    total_discount = sum((Decimal(str(n.invoice_discount)) for n in notes), Decimal("0"))
    assert total_discount <= Decimal("40.00"), (total_discount, standalone["number"])


def test_purchase_return_cancel_restores_exactly_the_fifo_layers_it_took(tenant_a):
    from inventory.models import InventoryCostLayer

    tenant_a.company.inventory_valuation_method = "FIFO"
    tenant_a.company.save(update_fields=["inventory_valuation_method"])
    product = make_product(tenant_a.company, sku="PRA-5", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    draft = create_draft_purchase(
        tenant_a, supplier,
        [
            {"product": product.id, "quantity": "3", "unit_price": "100", "gst_rate": "0"},
            {"product": product.id, "quantity": "3", "unit_price": "200", "gst_rate": "0"},
        ],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    layers = list(InventoryCostLayer.objects.filter(company=tenant_a.company, product=product).order_by("id"))

    def qty():
        rows = InventoryCostLayer.objects.filter(pk__in=[x.pk for x in layers]).order_by("id")
        return [Decimal(str(r.qty_remaining)) for r in rows]

    assert qty() == [Decimal("3"), Decimal("3")]
    first = _return(tenant_a, supplier, draft["id"], "2", product=product.id)
    second = _return(tenant_a, supplier, draft["id"], "2", product=product.id)
    assert _complete(tenant_a, first).status_code == 200
    assert qty() == [Decimal("1"), Decimal("3")]
    done_second = _complete(tenant_a, second)
    assert done_second.status_code == 200, done_second.data
    assert qty() == [Decimal("0"), Decimal("2")]
    # Cancel the first (middle) return: its two units go back on layer 1 only.
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{first}/cancel/").status_code == 200
    assert qty() == [Decimal("2"), Decimal("2")]
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{second}/cancel/").status_code == 200
    assert qty() == [Decimal("3"), Decimal("3")]


def test_preview_totals_matches_the_credit_note_and_persists_nothing(tenant_a):
    product = make_product(tenant_a.company, sku="PRP-1", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "NON_GST",
            "invoice_discount": "50",
            "additional_charges": "40",
            "items": [{"product": product.id, "quantity": "10", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{created.data['id']}/complete/").status_code == 200
    payload = {
        "supplier": supplier.id,
        "purchase_invoice": created.data["id"],
        "items": [{"product": product.id, "quantity": "4", "unit_price": "100", "gst_rate": "0"}],
    }
    returns_before = PurchaseReturn.objects.count()
    notes_before = PurchaseCreditNote.objects.count()
    preview = tenant_a.client.post("/api/v1/purchases/returns/preview-totals/", payload, format="json")
    assert preview.status_code == 200, preview.data
    assert PurchaseReturn.objects.count() == returns_before
    assert PurchaseCreditNote.objects.count() == notes_before

    ret = _return(tenant_a, supplier, created.data["id"], "4", product=product.id)
    assert _complete(tenant_a, ret).status_code == 200
    note = PurchaseCreditNote.objects.get(purchase_return_id=ret)
    assert Decimal(str(preview.data["grand_total"])) == note.grand_total
    assert Decimal(str(preview.data["taxable_total"])) == note.taxable_total


def test_preview_totals_reports_headroom_errors_and_caps_lines(tenant_a):
    product = make_product(tenant_a.company, sku="PRP-2", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    invoice_id, _src = _purchase(tenant_a, supplier, product, qty="2")
    over = tenant_a.client.post(
        "/api/v1/purchases/returns/preview-totals/",
        {"supplier": supplier.id, "purchase_invoice": invoice_id,
         "items": [{"product": product.id, "quantity": "9", "unit_price": "100", "gst_rate": "0"}]},
        format="json",
    )
    assert over.status_code == 400, over.data
    many = tenant_a.client.post(
        "/api/v1/purchases/returns/preview-totals/",
        {"supplier": supplier.id, "purchase_invoice": invoice_id,
         "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}] * 201},
        format="json",
    )
    assert many.status_code == 400, many.data
    assert "200" in str(many.data)
