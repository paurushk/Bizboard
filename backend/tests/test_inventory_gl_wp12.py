"""INV-WP-12 — stock writes that have no document behind them reach the books (inventory review #3).

Manual adjustments, count differences, expiry write-offs and serial scrap used to change the stock
value without a journal, so GL 1400 drifted from the valuation. With the company opt-in
(``ACCOUNTING_POST_STOCK_ADJUSTMENTS``) each posts Dr 5450 / Cr 1400 (loss) or the reverse (gain).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounting.models import JournalEntry
from accounting.reports import balance_sheet
from accounting.services import PostingService
from inventory.models import MovementType, SerialNumber, StockBalance, StockMovement
from inventory.services import InventoryService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db

FLAG = "ACCOUNTING_POST_STOCK_ADJUSTMENTS"


def _shop(flag=True):
    ns = seed_archetype("trader")
    if flag:
        ns.company.feature_flags = {FLAG: True}
        ns.company.save(update_fields=["feature_flags"])
    return ns


def _plain_product(ns, **filters):
    return next(
        p for p in ns.products
        if p.track_inventory and not p.track_batch and not p.track_serial
    )


def _opening(ns, product, qty="100", cost="50"):
    resp = ns.owner_client.post(
        "/api/v1/inventory/opening-stock/",
        {"product": product.id, "quantity": qty, "unit_cost": cost, "warehouse": ns.warehouses[0].id},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return resp.data


def _entries(ns, movement_id):
    return JournalEntry.objects.filter(
        company=ns.company, source_type="STOCK_MOVEMENT", source_id=movement_id, status="POSTED",
    )


def _sides(entry):
    return {line.account.code: (line.debit, line.credit) for line in entry.lines.select_related("account")}


def _adjust(ns, product, qty):
    resp = ns.owner_client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": qty, "reason": "Damaged / Defective Goods", "warehouse": ns.warehouses[0].id},
        format="json",
    )
    return resp


def test_a_loss_debits_shrinkage_and_credits_inventory():
    ns = _shop()
    product = _plain_product(ns)
    _opening(ns, product)
    resp = _adjust(ns, product, "-5")
    assert resp.status_code == 201, resp.data
    entry = _entries(ns, resp.data["id"]).get()
    assert entry.purpose == "STOCK_ADJUSTMENT"
    assert _sides(entry) == {"5450": (Decimal("250.00"), Decimal("0")), "1400": (Decimal("0"), Decimal("250.00"))}


def test_a_gain_debits_inventory_and_credits_shrinkage():
    ns = _shop()
    product = _plain_product(ns)
    _opening(ns, product)
    resp = _adjust(ns, product, "2")
    assert resp.status_code == 201, resp.data
    entry = _entries(ns, resp.data["id"]).get()
    assert _sides(entry) == {"1400": (Decimal("100.00"), Decimal("0")), "5450": (Decimal("0"), Decimal("100.00"))}


def test_a_count_difference_posts_a_journal_per_movement():
    ns = _shop()
    product = _plain_product(ns)
    _opening(ns, product)
    created = ns.owner_client.post("/api/v1/inventory/stock-counts/", {"warehouse": ns.warehouses[0].id}, format="json")
    sid = created.data["id"]
    line = next(l for l in created.data["lines"] if l["product"] == product.id)
    ns.owner_client.patch(
        f"/api/v1/inventory/stock-counts/{sid}/",
        {"lines": [{"id": l["id"], "counted_qty": "90" if l["id"] == line["id"] else l["system_qty"]} for l in created.data["lines"]]},
        format="json",
    )
    # A 10-unit difference is above the recheck limit: the counter names the line as rechecked.
    posted = ns.owner_client.post(
        f"/api/v1/inventory/stock-counts/{sid}/post/", {"rechecked_line_ids": [line["id"]]}, format="json",
    )
    assert posted.status_code == 200, posted.data
    move = StockMovement.objects.get(company=ns.company, product=product, reference_type="stock_count")
    entry = _entries(ns, move.id).get()
    assert entry.purpose == "STOCK_COUNT"
    assert _sides(entry)["5450"] == (Decimal("500.00"), Decimal("0"))


def test_expiry_write_off_and_serial_scrap_post_too():
    ns = _shop()
    batch_product = next(p for p in ns.products if p.track_batch)
    resp = ns.owner_client.post(
        "/api/v1/inventory/opening-stock/",
        {
            "product": batch_product.id, "quantity": 10, "unit_cost": 20, "warehouse": ns.warehouses[0].id,
            "batch_no": "EXP-1", "expiry_date": str(date.today() + timedelta(days=5)),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    batch_id = StockMovement.objects.filter(company=ns.company, product=batch_product).first().batch_id
    wo = ns.owner_client.post(
        "/api/v1/inventory/alerts/expiry/",
        {"product": batch_product.id, "warehouse": ns.warehouses[0].id, "batch": batch_id, "quantity": 4},
        format="json",
    )
    assert wo.status_code == 201, wo.data
    entry = _entries(ns, wo.data["id"]).get()
    assert entry.purpose == "STOCK_EXPIRY" and _sides(entry)["5450"][0] == Decimal("80.00")

    serial_product = next((p for p in ns.products if p.track_serial), None)
    if serial_product is not None:
        InventoryService.post_opening(
            company=ns.company, product=serial_product, quantity=1, serial_numbers=["GL-S1"],
            unit_cost=Decimal("300"), warehouse=ns.warehouses[0], user=ns.owner,
        )
        serial = SerialNumber.objects.get(company=ns.company, serial_number="GL-S1")
        scrap = ns.owner_client.post(f"/api/v1/inventory/serials/{serial.id}/transition/", {"status": "SCRAPPED"}, format="json")
        assert scrap.status_code == 200, scrap.data
        move = StockMovement.objects.get(company=ns.company, reference_type="serial_scrap", reference_id=str(serial.id))
        assert _entries(ns, move.id).get().purpose == "SERIAL_SCRAP"


def test_nothing_posts_until_the_company_opts_in():
    ns = _shop(flag=False)
    product = _plain_product(ns)
    _opening(ns, product)
    resp = _adjust(ns, product, "-5")
    assert resp.status_code == 201
    assert not _entries(ns, resp.data["id"]).exists()


def test_posting_is_idempotent_and_skips_movements_that_are_not_stock_writes():
    ns = _shop()
    product = _plain_product(ns)
    _opening(ns, product)
    resp = _adjust(ns, product, "-1")
    move = StockMovement.objects.get(pk=resp.data["id"])
    PostingService.post_stock_adjustment(move, ns.owner)
    PostingService.post_stock_adjustment(move, ns.owner)
    assert _entries(ns, move.id).count() == 1
    # a transfer reversal is an adjustment movement too, but moves stock between godowns
    other = InventoryService.post_movement(
        company=ns.company, product=product, movement_type=MovementType.ADJUSTMENT, quantity=Decimal("-1"),
        reference_type="stock_transfer_cancel", reason="x", user=ns.owner, warehouse=ns.warehouses[0],
    )
    assert PostingService.post_stock_adjustment(other, ns.owner) is None
    assert not _entries(ns, other.id).exists()


def test_a_refused_journal_refuses_the_stock_change_too():
    ns = _shop()
    product = _plain_product(ns)
    _opening(ns, product)
    ns.company.books_start_date = date.today() + timedelta(days=30)
    ns.company.save(update_fields=["books_start_date"])
    before = StockBalance.objects.get(company=ns.company, product=product).on_hand
    resp = _adjust(ns, product, "-5")
    assert resp.status_code >= 400
    assert StockBalance.objects.get(company=ns.company, product=product).on_hand == before


def test_inventory_in_the_books_matches_the_stock_value_after_write_offs():
    ns = _shop()
    product = _plain_product(ns)
    _opening(ns, product, qty="100", cost="50")
    _adjust(ns, product, "-5")
    _adjust(ns, product, "2")
    sheet = balance_sheet(ns.company)
    assert sheet["inventory_gl"] == sheet["inventory_valuation"] == Decimal("4850.00")
    assert sheet["inventory_variance"] == 0


def test_without_the_opt_in_the_books_drift_from_stock_value():
    ns = _shop(flag=False)
    product = _plain_product(ns)
    _opening(ns, product, qty="100", cost="50")
    _adjust(ns, product, "-5")
    sheet = balance_sheet(ns.company)
    assert sheet["inventory_gl"] == Decimal("5000.00")
    assert sheet["inventory_valuation"] == Decimal("4750.00")
    assert sheet["inventory_variance"] == Decimal("-250.00")


def test_backfill_posts_the_past_once_and_needs_the_flag():
    ns = _shop(flag=False)
    product = _plain_product(ns)
    _opening(ns, product)
    first = _adjust(ns, product, "-5").data["id"]
    second = _adjust(ns, product, "3").data["id"]
    with pytest.raises(CommandError):
        call_command("backfill_stock_adjustment_journals", company_id=ns.company.id, stdout=StringIO())

    ns.company.feature_flags = {FLAG: True}
    ns.company.save(update_fields=["feature_flags"])
    out = StringIO()
    call_command("backfill_stock_adjustment_journals", company_id=ns.company.id, stdout=out)
    assert "2 stock write(s) have no journal" in out.getvalue() and "Dry run" in out.getvalue()
    assert not _entries(ns, first).exists()

    call_command("backfill_stock_adjustment_journals", company_id=ns.company.id, apply=True, stdout=StringIO())
    assert _entries(ns, first).count() == 1 and _entries(ns, second).count() == 1
    again = StringIO()
    call_command("backfill_stock_adjustment_journals", company_id=ns.company.id, apply=True, stdout=again)
    assert "0 stock write(s) have no journal" in again.getvalue()
    assert balance_sheet(ns.company)["inventory_variance"] == 0


def test_the_valuation_report_shows_stock_value_beside_the_books():
    ns = _shop(flag=False)
    product = _plain_product(ns)
    _opening(ns, product, qty="100", cost="50")
    _adjust(ns, product, "-5")
    body = ns.owner_client.get("/api/v1/inventory/valuation/").data
    body = body.get("data", body)
    assert Decimal(str(body["stock_value"])) == Decimal("4750.00")
    assert Decimal(str(body["inventory_in_books"])) == Decimal("5000.00")
    assert Decimal(str(body["books_variance"])) == Decimal("-250.00")
    assert body["stock_writes_posted"] is False

    ns.company.feature_flags = {FLAG: True}
    ns.company.save(update_fields=["feature_flags"])
    call_command("backfill_stock_adjustment_journals", company_id=ns.company.id, apply=True, stdout=StringIO())
    again = ns.owner_client.get("/api/v1/inventory/valuation/").data
    again = again.get("data", again)
    assert Decimal(str(again["books_variance"])) == 0 and again["stock_writes_posted"] is True


def test_a_godown_view_is_not_compared_with_the_whole_books():
    ns = _shop(flag=False)
    product = _plain_product(ns)
    _opening(ns, product)
    body = ns.owner_client.get("/api/v1/inventory/valuation/", {"warehouse": ns.warehouses[0].id}).data
    body = body.get("data", body)
    assert "books_variance" not in body
