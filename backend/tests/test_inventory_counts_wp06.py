"""INV-WP-06 — stock count review, surplus lines, part counts, drift marker (inventory review #4, #5)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockBalance, StockCountLine, StockCountSession, StockMovement
from inventory.services import InventoryService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

COUNTS = "/api/v1/inventory/stock-counts/"


def _on_hand(company, product):
    return sum(
        (b.on_hand for b in StockBalance.objects.filter(company=company, product=product)), Decimal("0")
    )


def _session(tenant, *products, blind=False):
    resp = tenant.client.post(COUNTS, {"warehouse": InventoryService.default_warehouse(tenant.company).id, "blind": blind}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _save(tenant, session_id, lines):
    resp = tenant.client.patch(f"{COUNTS}{session_id}/", {"lines": lines}, format="json")
    assert resp.status_code == 200, resp.data
    return resp.data


def _post(tenant, session_id, body=None):
    return tenant.client.post(f"{COUNTS}{session_id}/post/", body or {}, format="json")


def _line_for(session, product):
    return next(line for line in session["lines"] if line["product"] == product.id)


def test_review_shows_variance_value_and_recheck_flag(tenant_a):
    cheap = make_product(tenant_a.company, sku="C-1", purchase_price="10")
    dear = make_product(tenant_a.company, sku="C-2", purchase_price="5000")
    add_stock(tenant_a, cheap, "100")
    add_stock(tenant_a, dear, "10")
    session = _session(tenant_a)
    _save(tenant_a, session["id"], [
        {"id": _line_for(session, cheap)["id"], "counted_qty": "99"},
        {"id": _line_for(session, dear)["id"], "counted_qty": "8"},
    ])
    review = tenant_a.client.get(f"{COUNTS}{session['id']}/review/")
    assert review.status_code == 200, review.data
    by_product = {line["product"]: line for line in review.data["lines"]}
    assert Decimal(by_product[cheap.id]["variance"]) == Decimal("-1")
    assert Decimal(by_product[cheap.id]["variance_value_estimate"]) == Decimal("-10.00")
    assert by_product[cheap.id]["needs_recheck"] is False
    # two units of a Rs 5,000 item is Rs 10,000: worth a second look even though it is only 2 units
    assert Decimal(by_product[dear.id]["variance_value_estimate"]) == Decimal("-10000.00")
    assert by_product[dear.id]["needs_recheck"] is True


def test_blind_counter_never_sees_system_quantity_but_review_does(tenant_a):
    product = make_product(tenant_a.company, sku="B-1")
    add_stock(tenant_a, product, "10")
    session = _session(tenant_a, blind=True)
    counter = tenant_a.client.get(f"{COUNTS}{session['id']}/counter/")
    assert counter.status_code == 200
    for line in counter.data["lines"]:
        assert "system_qty" not in line
        assert "variance_value_estimate" not in line
        assert "needs_recheck" not in line
    review = tenant_a.client.get(f"{COUNTS}{session['id']}/review/")
    assert "system_qty" in review.data["lines"][0]


def test_found_stock_can_be_added_and_posts_a_gain(tenant_a):
    known = make_product(tenant_a.company, sku="F-1")
    surplus = make_product(tenant_a.company, sku="F-2")
    add_stock(tenant_a, known, "10")
    session = _session(tenant_a)
    _save(tenant_a, session["id"], [{"id": _line_for(session, known)["id"], "counted_qty": "10"}])

    added = tenant_a.client.post(
        f"{COUNTS}{session['id']}/add-line/", {"product": surplus.id, "counted_qty": "4"}, format="json"
    )
    assert added.status_code == 201, added.data
    line = _line_for(added.data, surplus)
    assert Decimal(line["system_qty"]) == Decimal("0")
    assert added.data["status"] == "COUNTED"

    posted = _post(tenant_a, session["id"])
    assert posted.status_code == 200, posted.data
    assert _on_hand(tenant_a.company, surplus) == Decimal("4")
    assert StockMovement.objects.filter(
        company=tenant_a.company, product=surplus, reference_type="stock_count", movement_type=MovementType.ADJUSTMENT
    ).exists()


def test_adding_the_same_item_again_updates_its_count(tenant_a):
    product = make_product(tenant_a.company, sku="F-3")
    session = _session(tenant_a)
    for qty in ("2", "5"):
        resp = tenant_a.client.post(
            f"{COUNTS}{session['id']}/add-line/", {"product": product.id, "counted_qty": qty}, format="json"
        )
        assert resp.status_code in (200, 201), resp.data
    lines = StockCountLine.objects.filter(session_id=session["id"], product=product)
    assert lines.count() == 1
    assert lines.get().counted_qty == Decimal("5")


def test_add_line_needs_a_batch_for_a_batch_tracked_item_and_a_session_that_is_still_open(tenant_a):
    tracked = make_product(tenant_a.company, sku="F-4", track_batch=True)
    plain = make_product(tenant_a.company, sku="F-5")
    add_stock(tenant_a, plain, "3")
    session = _session(tenant_a)
    refused = tenant_a.client.post(
        f"{COUNTS}{session['id']}/add-line/", {"product": tracked.id, "counted_qty": "1"}, format="json"
    )
    assert refused.status_code == 400
    _save(tenant_a, session["id"], [{"id": _line_for(session, plain)["id"], "counted_qty": "3"}])
    assert _post(tenant_a, session["id"]).status_code == 200
    late = tenant_a.client.post(
        f"{COUNTS}{session['id']}/add-line/", {"product": plain.id, "counted_qty": "1"}, format="json"
    )
    assert late.status_code == 400


def test_a_part_count_posts_only_the_counted_lines(tenant_a):
    counted = make_product(tenant_a.company, sku="P-1")
    left_out = make_product(tenant_a.company, sku="P-2")
    add_stock(tenant_a, counted, "10")
    add_stock(tenant_a, left_out, "10")
    session = _session(tenant_a)
    saved = _save(tenant_a, session["id"], [
        {"id": _line_for(session, counted)["id"], "counted_qty": "7"},
        {"id": _line_for(session, left_out)["id"], "skipped": True},
    ])
    assert saved["status"] == "COUNTED"
    assert _post(tenant_a, session["id"]).status_code == 200
    assert _on_hand(tenant_a.company, counted) == Decimal("7")
    assert _on_hand(tenant_a.company, left_out) == Decimal("10")


def test_unskipping_an_uncounted_line_reopens_the_session(tenant_a):
    counted = make_product(tenant_a.company, sku="U-1")
    other = make_product(tenant_a.company, sku="U-2")
    add_stock(tenant_a, counted, "5")
    add_stock(tenant_a, other, "5")
    session = _session(tenant_a)
    other_line = _line_for(session, other)["id"]
    _save(tenant_a, session["id"], [
        {"id": _line_for(session, counted)["id"], "counted_qty": "5"},
        {"id": other_line, "skipped": True},
    ])
    assert StockCountSession.objects.get(pk=session["id"]).status == StockCountSession.Status.COUNTED
    reopened = _save(tenant_a, session["id"], [{"id": other_line, "skipped": False}])
    assert reopened["status"] == "DRAFT"
    assert _post(tenant_a, session["id"]).status_code == 400


def test_a_count_with_every_line_skipped_cannot_be_posted(tenant_a):
    product = make_product(tenant_a.company, sku="S-1")
    add_stock(tenant_a, product, "5")
    session = _session(tenant_a)
    _save(tenant_a, session["id"], [{"id": _line_for(session, product)["id"], "skipped": True}])
    resp = _post(tenant_a, session["id"])
    assert resp.status_code == 400
    assert "at least one" in str(resp.data).lower()


def test_keep_server_marks_the_lines_it_did_not_reconcile(tenant_a):
    drifted = make_product(tenant_a.company, sku="D-1")
    steady = make_product(tenant_a.company, sku="D-2")
    add_stock(tenant_a, drifted, "10")
    add_stock(tenant_a, steady, "10")
    session = _session(tenant_a)
    _save(tenant_a, session["id"], [
        {"id": _line_for(session, drifted)["id"], "counted_qty": "8"},
        {"id": _line_for(session, steady)["id"], "counted_qty": "9"},
    ])
    # a sale-like movement after the sheet was printed: the system quantity is no longer 10
    InventoryService.post_movement(
        company=tenant_a.company, product=drifted, movement_type=MovementType.ADJUSTMENT, quantity=Decimal("-1"),
        reason="after sheet", user=tenant_a.owner,
    )
    conflict = _post(tenant_a, session["id"])
    assert conflict.status_code == 409 or conflict.status_code == 400, conflict.data
    resolved = _post(tenant_a, session["id"], {"resolve_conflicts": "KEEP_SERVER"})
    assert resolved.status_code == 200, resolved.data
    by_product = {line["product"]: line for line in resolved.data["lines"]}
    assert by_product[drifted.id]["drift_skipped"] is True
    assert by_product[steady.id]["drift_skipped"] is False
    assert _on_hand(tenant_a.company, drifted) == Decimal("9")
    assert _on_hand(tenant_a.company, steady) == Decimal("9")


def test_count_lines_carry_the_code_and_barcode_a_scan_matches_against(tenant_a):
    product = make_product(tenant_a.company, sku="SCAN-1", name="Soap")
    product.barcode = "8901234500001"
    product.save(update_fields=["barcode"])
    add_stock(tenant_a, product, "5")
    session = _session(tenant_a)
    line = _line_for(session, product)
    assert line["product_sku"] == "SCAN-1"
    assert line["product_barcode"] == "8901234500001"
