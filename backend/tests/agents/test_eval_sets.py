"""Evaluation sets for Collections (AGT-209), Inventory Risk (AGT-406) and Bill Check (AGT-505).

These are SYNTHETIC cases built to exercise the rules across their range (30+ each). They are not pilot data: each
asserts the property the plan sets as the threshold (no invented numbers, quantities equal the service output, zero
wrong suggestions, precision at least 0.9 against the existing 3-way match). Extend them with real, anonymised cases
from the pilot before quoting any accuracy figure.
"""

from decimal import Decimal

import pytest

from agents import numbers, tax_policy
from agents.catalog.collections import context as col_ctx
from agents.enums import RunStatus
from agents.models import AgentProposal
from core.exceptions import BusinessRuleError
from inventory.models import BatchLot, WarehouseReorderLevel
from inventory.planning import purchase_plan
from purchases.services import PurchaseService

from .test_bill_check import bc, bill_off_order, codes  # noqa: F401  (fixture re-export)
from .test_collections import col, overdue_invoice, run_for  # noqa: F401
from .test_inventory_risk import iv, short_item, stock, sweep  # noqa: F401
from tests.conftest import make_product

pytestmark = pytest.mark.django_db


# --- Bill Check: 36 cases ----------------------------------------------------------------------
RATES = ["100", "100.40", "100.60", "101", "120", "90"]
QTYS = ["10", "12", "8"]
GSTS = ["0", "18"]
BILL_CASES = [(r, q, g) for r in RATES for q in QTYS for g in GSTS]


def expected_codes(rate, qty, gst):
    """The rules written out independently of the comparator: PO is 10 at 100.00, GST 0."""
    out = set()
    rate = Decimal(rate)
    if abs(rate - Decimal("100")) > max(Decimal("0.01"), (Decimal("100") * Decimal("0.005")).quantize(Decimal("0.01"))):
        out.add("RATE_DIFF")
    if Decimal(qty) > Decimal("10"):
        out.add("QTY_OVER_PO")
    if gst != "0":
        out.add("GST_RATE_DIFF")
    return out


def test_bill_check_eval_matches_the_written_rules_and_the_existing_three_way_match(bc):  # noqa: F811
    assert len(BILL_CASES) >= 30
    tp = fp = fn = agree = 0
    for i, (rate, qty, gst) in enumerate(BILL_CASES):
        bill = bill_off_order(bc, bill_rate=rate, bill_qty=qty, bill_gst=gst, number=f"EV{i}")
        got, want = codes(bill), expected_codes(rate, qty, gst)
        tp += len(got & want)
        fp += len(got - want)
        fn += len(want - got)
        try:
            PurchaseService.match_bill_to_po(bill)
            blocked = False
        except BusinessRuleError:
            blocked = True
        agree += blocked == bool({"RATE_DIFF", "QTY_OVER_PO", "NOT_ON_PO"} & got)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    # The rules are deterministic, so anything under 1.0 is a real difference (the plan's floor was 0.9).
    assert precision == 1.0 and recall == 1.0, (precision, recall)
    assert agree == len(BILL_CASES), "the agent and the 3-way match disagree on a bill"


# --- Inventory Risk: 32 cases ------------------------------------------------------------------
INV_CASES = [(n, m) for n in ("0", "1", "2", "4", "6", "8") for m in ("0", "3", "5", "9", "20", "50")][:36]


def test_inventory_eval_quantities_equal_the_planning_output_and_never_exceed_the_donor(iv):  # noqa: F811
    assert len(INV_CASES) >= 30
    wrong = 0
    for i, (north, main) in enumerate(INV_CASES):
        short_item(iv, name=f"Item{i}", sku=f"EV{i}", north_stock=None if north == "0" else north, main_stock=None if main == "0" else main)
    plan = purchase_plan(iv.company)["rows"]
    run = sweep(iv)
    assert run.status == RunStatus.SUCCEEDED
    moved, bought = {}, {}
    for p in AgentProposal.objects.filter(run=run):
        target = moved if p.kind == "STOCK_TRANSFER" else bought
        for line in p.payload["lines"]:
            target[line["product_id"]] = target.get(line["product_id"], Decimal("0")) + Decimal(line["qty"])
    for row in plan:
        qty = Decimal(row["suggested_qty"])
        pid = row["product_id"]
        if row["transfer_from_warehouse_id"]:
            wrong += moved.get(pid) != qty
        elif row["supplier_id"]:
            wrong += bought.get(pid) != qty
    assert wrong == 0, f"{wrong} suggestion(s) differ from the planning rows"
    assert len(plan) >= 30 - 6  # the grid includes cases that are not short at all


def test_inventory_eval_lots_never_expired_or_held(iv):  # noqa: F811
    from datetime import timedelta

    from django.utils import timezone

    today = timezone.localdate()
    milk = make_product(iv.company, sku="EVM", name="Milk", reorder_level="0", track_batch=True)
    lots = [
        BatchLot.objects.create(company=iv.company, product=milk, batch_no=f"L{i}",
                                expiry_date=today + timedelta(days=(-3 if i % 3 == 0 else 40 + i)),
                                quality_status="HOLD" if i % 3 == 1 else "RELEASED")
        for i in range(9)
    ]
    for lot in lots:
        stock(iv, milk, iv.main, "4", batch=lot)
    stock(iv, milk, iv.north, "1", batch=lots[2])
    WarehouseReorderLevel.objects.create(company=iv.company, warehouse=iv.north, product=milk, reorder_level=Decimal("15"))
    run = sweep(iv)
    used = {l["batch_no"] for p in AgentProposal.objects.filter(run=run, kind="STOCK_TRANSFER") for l in p.payload["lines"]}
    assert used and all(int(b[1:]) % 3 == 2 for b in used), used  # only released, unexpired lots


# --- Collections: 30 cases ---------------------------------------------------------------------
@pytest.mark.parametrize("days", list(range(2, 32)))
def test_collections_eval_numbers_trace_to_the_ledger(col, days):  # noqa: F811
    inv = overdue_invoice(col, days=days, name=f"Party{days}")
    run = run_for(col, f"AR_CUSTOMER:{inv.customer_id}")
    assert run.status == RunStatus.SUCCEEDED
    [p] = AgentProposal.objects.filter(run=run)
    from ledgers.services import LedgerService

    owed = LedgerService.customer_outstanding(col.company, inv.customer)
    assert Decimal(p.payload["total_overdue"]) == owed
    facts = col_ctx.customer_facts(col.company, inv.customer, __import__("django.utils.timezone", fromlist=["x"]).localdate())
    for variant in p.payload["variants"].values():
        assert not numbers.invented_numbers(variant, [facts, col.company.name], cited_count=len(p.evidence))
        assert not tax_policy.violates(variant)
    assert any(e["type"] == "invoice" and e["id"] == inv.id for e in p.evidence)
