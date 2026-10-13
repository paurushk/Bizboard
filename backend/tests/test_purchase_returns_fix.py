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
