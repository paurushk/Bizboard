"""INV-IDR-04 - counts that survive a busy godown: drift per line, no overwriting another counter,
one open count per godown, negative balances on the sheet."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from inventory.models import MovementType, StockBalance, StockCountLine, StockCountSession, StockMovement
from inventory.services import InventoryService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

COUNTS = "/api/v1/inventory/stock-counts/"


def _on_hand(company, product):
    return sum((b.on_hand for b in StockBalance.objects.filter(company=company, product=product)), Decimal("0"))


def _open(client, tenant):
    resp = client.post(COUNTS, {"warehouse": InventoryService.default_warehouse(tenant.company).id}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _line(session, product):
    return next(row for row in session["lines"] if row["product"] == product.id)


def _count(client, session_id, line_id, qty, **extra):
    return client.patch(
        f"{COUNTS}{session_id}/", {"lines": [{"id": line_id, "counted_qty": str(qty), **extra}]}, format="json",
    )


def _sell(tenant, product, qty):
    InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=MovementType.SALE, quantity=Decimal(qty),
        user=tenant.owner, skip_negative_check=True,
    )


def _second_counter(tenant, email="counter2-idr04@alpha.test"):
    user = User.objects.create_user(email=email, password="StrongPass123!")
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=CompanyUser.Role.MANAGER, can_manage_inventory=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---- one open count per godown ---------------------------------------------------------------

def test_a_second_open_count_for_the_same_godown_is_refused_until_the_first_is_closed(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-O1")
    add_stock(tenant_a, product, "10")
    first = _open(tenant_a.client, tenant_a)
    again = tenant_a.client.post(
        COUNTS, {"warehouse": InventoryService.default_warehouse(tenant_a.company).id}, format="json",
    )
    assert again.status_code == 400, again.data
    assert "count_already_open" in str(again.data)
    assert tenant_a.client.post(f"{COUNTS}{first['id']}/cancel/").status_code == 200
    assert tenant_a.client.post(
        COUNTS, {"warehouse": InventoryService.default_warehouse(tenant_a.company).id}, format="json",
    ).status_code == 201


# ---- negative balances are on the sheet ------------------------------------------------------

def test_an_item_with_a_negative_balance_is_on_the_sheet_so_a_count_can_correct_it(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-N1")
    _sell(tenant_a, product, 3)  # stock is now -3
    assert _on_hand(tenant_a.company, product) == Decimal("-3")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    assert Decimal(line["system_qty"]) == Decimal("-3")
    assert _count(tenant_a.client, session["id"], line["id"], 0).status_code == 200
    posted = tenant_a.client.post(f"{COUNTS}{session['id']}/post/", {}, format="json")
    assert posted.status_code == 200, posted.data
    assert _on_hand(tenant_a.company, product) == Decimal("0")


# ---- line versions ---------------------------------------------------------------------------

def test_saving_a_line_another_counter_changed_is_refused_with_their_value(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-V1")
    add_stock(tenant_a, product, "10")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    assert line["version"] == 0
    other = _second_counter(tenant_a)

    assert _count(other, session["id"], line["id"], 9, version=0).status_code == 200
    mine = _count(tenant_a.client, session["id"], line["id"], 7, version=0)
    assert mine.status_code == 409, mine.data
    assert "STOCK_COUNT_LINE_CHANGED" in str(mine.data)
    assert "9" in str(mine.data)
    assert StockCountLine.objects.get(pk=line["id"]).counted_qty == Decimal("9")


def test_a_client_that_sends_no_version_is_not_checked(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-V2")
    add_stock(tenant_a, product, "10")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    other = _second_counter(tenant_a)
    assert _count(other, session["id"], line["id"], 9, version=0).status_code == 200
    assert _count(tenant_a.client, session["id"], line["id"], 7).status_code == 200


def test_saving_the_same_value_again_does_not_bump_the_version(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-V3")
    add_stock(tenant_a, product, "10")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    first = _count(tenant_a.client, session["id"], line["id"], 9, version=0)
    assert _line(first.data, product)["version"] == 1
    second = _count(tenant_a.client, session["id"], line["id"], 9, version=1)
    assert second.status_code == 200
    assert _line(second.data, product)["version"] == 1


def test_an_empty_line_list_changes_nothing(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-E1")
    add_stock(tenant_a, product, "10")
    session = _open(tenant_a.client, tenant_a)
    resp = tenant_a.client.patch(f"{COUNTS}{session['id']}/", {"lines": []}, format="json")
    assert resp.status_code == 200, resp.data
    assert StockCountLine.objects.filter(session_id=session["id"]).count() == 1


# ---- drift: sales while counting -------------------------------------------------------------

def test_a_sale_after_the_count_is_not_subtracted_twice_when_the_count_is_adjusted_for_movements(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-D1")
    add_stock(tenant_a, product, "100")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    assert _count(tenant_a.client, session["id"], line["id"], 100).status_code == 200  # shelf had 100
    _sell(tenant_a, product, 10)  # a sale after the counting
    conflict = tenant_a.client.post(f"{COUNTS}{session['id']}/post/", {}, format="json")
    assert conflict.status_code == 409, conflict.data
    assert "STOCK_COUNT_CONFLICT" in str(conflict.data)

    posted = tenant_a.client.post(
        f"{COUNTS}{session['id']}/post/", {"resolutions": {str(line["id"]): "ADJUST_FOR_MOVEMENTS"}}, format="json",
    )
    assert posted.status_code == 200, posted.data
    assert _on_hand(tenant_a.company, product) == Decimal("90")  # the sale stands; nothing was added back


def test_keeping_the_local_count_adds_the_sale_back_which_is_why_adjusting_is_the_default(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-D2")
    add_stock(tenant_a, product, "100")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    _count(tenant_a.client, session["id"], line["id"], 100)
    _sell(tenant_a, product, 10)
    posted = tenant_a.client.post(
        f"{COUNTS}{session['id']}/post/", {"rechecked_line_ids": [line["id"]], "resolve_conflicts": "KEEP_LOCAL"},
        format="json",
    )
    assert posted.status_code == 200, posted.data
    assert _on_hand(tenant_a.company, product) == Decimal("100")


def test_a_sale_made_before_the_item_was_counted_is_part_of_the_count(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-D3")
    add_stock(tenant_a, product, "100")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    _sell(tenant_a, product, 10)  # sold while the counter walked to the shelf
    _count(tenant_a.client, session["id"], line["id"], 90)  # the shelf had 90
    posted = tenant_a.client.post(
        f"{COUNTS}{session['id']}/post/", {"resolutions": {str(line["id"]): "ADJUST_FOR_MOVEMENTS"}}, format="json",
    )
    assert posted.status_code == 200, posted.data
    assert _on_hand(tenant_a.company, product) == Decimal("90")
    assert not StockMovement.objects.filter(
        company=tenant_a.company, product=product, reference_type="stock_count"
    ).exists()


def test_a_real_loss_is_still_posted_when_the_count_is_adjusted_for_a_sale(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-D4")
    add_stock(tenant_a, product, "100")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    _sell(tenant_a, product, 10)
    _count(tenant_a.client, session["id"], line["id"], 88)  # 90 expected, 2 missing
    # The sheet said 100 and the counter found 88: a large difference the counter ticks as rechecked.
    posted = tenant_a.client.post(
        f"{COUNTS}{session['id']}/post/",
        {"resolutions": {str(line["id"]): "ADJUST_FOR_MOVEMENTS"}, "rechecked_line_ids": [line["id"]]},
        format="json",
    )
    assert posted.status_code == 200, posted.data
    assert _on_hand(tenant_a.company, product) == Decimal("88")


def test_each_drifted_line_gets_its_own_answer(tenant_a):
    first = make_product(tenant_a.company, sku="IDR4-M1")
    second = make_product(tenant_a.company, sku="IDR4-M2")
    add_stock(tenant_a, first, "50")
    add_stock(tenant_a, second, "50")
    session = _open(tenant_a.client, tenant_a)
    line_a, line_b = _line(session, first), _line(session, second)
    _count(tenant_a.client, session["id"], line_a["id"], 50)
    _count(tenant_a.client, session["id"], line_b["id"], 50)
    _sell(tenant_a, first, 5)
    _sell(tenant_a, second, 5)
    posted = tenant_a.client.post(
        f"{COUNTS}{session['id']}/post/",
        {"resolutions": {str(line_a["id"]): "KEEP_SERVER", str(line_b["id"]): "ADJUST_FOR_MOVEMENTS"}},
        format="json",
    )
    assert posted.status_code == 200, posted.data
    assert StockCountLine.objects.get(pk=line_a["id"]).drift_skipped is True
    assert StockCountLine.objects.get(pk=line_b["id"]).drift_skipped is False
    assert _on_hand(tenant_a.company, first) == Decimal("45")
    assert _on_hand(tenant_a.company, second) == Decimal("45")


def test_an_unknown_resolution_is_refused(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-R1")
    add_stock(tenant_a, product, "10")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    _count(tenant_a.client, session["id"], line["id"], 10)
    resp = tenant_a.client.post(
        f"{COUNTS}{session['id']}/post/", {"resolutions": {str(line["id"]): "SHRUG"}}, format="json",
    )
    assert resp.status_code == 400, resp.data


# ---- "count equals system" is recorded -------------------------------------------------------

def test_a_line_filled_from_the_system_quantity_is_marked_and_the_mark_clears_when_it_is_counted(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-F1")
    add_stock(tenant_a, product, "10")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    filled = _count(tenant_a.client, session["id"], line["id"], 10, version=0, filled_from_system=True)
    assert _line(filled.data, product)["filled_from_system"] is True
    review = tenant_a.client.get(f"{COUNTS}{session['id']}/review/")
    assert _line(review.data, product)["filled_from_system"] is True
    counted = _count(tenant_a.client, session["id"], line["id"], 9, version=1)
    assert _line(counted.data, product)["filled_from_system"] is False


# ---- cancel ----------------------------------------------------------------------------------

def test_a_posted_count_cannot_be_cancelled(tenant_a):
    product = make_product(tenant_a.company, sku="IDR4-C1")
    add_stock(tenant_a, product, "10")
    session = _open(tenant_a.client, tenant_a)
    line = _line(session, product)
    _count(tenant_a.client, session["id"], line["id"], 10)
    assert tenant_a.client.post(f"{COUNTS}{session['id']}/post/", {}, format="json").status_code == 200
    assert tenant_a.client.post(f"{COUNTS}{session['id']}/cancel/").status_code == 400
    assert StockCountSession.objects.get(pk=session["id"]).status == StockCountSession.Status.POSTED
