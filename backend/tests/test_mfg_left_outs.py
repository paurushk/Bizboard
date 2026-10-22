"""QOS-0148: the work order list export and the batch label."""

import csv
import io
from decimal import Decimal

import pytest

from manufacturing.services import issue as issue_svc, receipt as receipt_svc, release_work_order
from tests.conftest import make_product
from tests.mfg_helpers import make_bom, make_wo, member, prepare, stocked

pytestmark = pytest.mark.django_db

BASE = "/api/v1/manufacturing"


def world(tenant):
    company = prepare(tenant, method="WAVG")
    fg = make_product(company, sku="LO-FG", name="Label biscuit", track_batch=True)
    comp = stocked(tenant, "LO-C", 1000, 10)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant.owner)
    done = release_work_order(make_wo(company, bom, 10, user=tenant.owner, batch_no="LO-B1"), tenant.owner)
    issue_svc.post_issue(issue_svc.create_issue(done, tenant.owner), tenant.owner)
    rec = receipt_svc.post_receipt(receipt_svc.create_receipt(done, tenant.owner, {
        "is_final": True, "batch_no": "LO-B1", "exp_date": "2031-02-03", "lines": [{"kind": "MAIN", "qty_good": 10}],
    }), tenant.owner)
    open_wo = release_work_order(make_wo(company, bom, 5, user=tenant.owner), tenant.owner)
    return company, done, rec, open_wo


def table(resp):
    return list(csv.reader(io.StringIO(resp.content.decode())))


def test_work_order_export_follows_the_filters_and_hides_cost_from_the_floor(tenant_a):
    _c, done, _rec, open_wo = world(tenant_a)
    everything = tenant_a.client.get(f"{BASE}/work-orders/export/")
    assert everything.status_code == 200 and everything["Content-Type"].startswith("text/csv")
    rows = table(everything)
    assert rows[0][:5] == ["Number", "Item", "Status", "Planned", "Made"] and "Variance" in rows[0]
    assert {r[0] for r in rows[1:]} == {done.number, open_wo.number}
    mine = {r[0]: r for r in rows[1:]}
    assert mine[done.number][3] == "10.000" and Decimal(mine[done.number][4]) == Decimal("10")
    released_only = table(tenant_a.client.get(f"{BASE}/work-orders/export/", {"status": "RELEASED"}))
    assert [r[0] for r in released_only[1:]] == [open_wo.number]
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    seen = table(floor.get(f"{BASE}/work-orders/export/"))
    assert "Variance" not in seen[0] and len(seen[0]) == 10


def test_the_batch_label_shows_the_batch_dates_and_no_money(tenant_a):
    _c, done, rec, _open = world(tenant_a)
    page = tenant_a.client.get(f"{BASE}/production-receipts/{rec.pk}/print-label/", {"copies": "3"})
    assert page.status_code == 200 and page["Content-Type"].startswith("text/html")
    html = page.content.decode()
    assert html.count('class="label"') == 3
    assert "LO-B1" in html and "Label biscuit" in html and "2031-02-03" in html and done.number in html
    assert "₹" not in html
    huge = tenant_a.client.get(f"{BASE}/production-receipts/{rec.pk}/print-label/", {"copies": "999"})
    assert huge.content.decode().count('class="label"') == 50           # capped
