# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)
"""Block J: time and query budgets so a slow or chatty change to an agent fails a test. The budgets are generous
(about twice what was measured on 2026-10-21); they catch a per-row query or a quadratic loop, not small drift."""

import time
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from agents import runner, services
from agents.catalog.order_intake import resolver
from agents.enums import Trigger
from agents.models import AgentProposal
from masters.models import Product
from purchases.models import PurchaseInvoice, PurchaseItem
from tests.conftest import make_product

from .test_bill_check import bc  # noqa: F401
from .test_inventory_risk import iv, stock  # noqa: F401
from .test_order_intake import oi  # noqa: F401

pytestmark = pytest.mark.django_db


def test_the_product_index_stays_fast_with_5000_products(oi):
    Product.objects.bulk_create([
        Product(company=oi.company, name=f"Generic Item {i:05d} Pack", sku=f"G{i:05d}", selling_price=Decimal("10"), gst_rate=Decimal("5"))
        for i in range(5000)
    ])
    started = time.perf_counter()
    index = resolver.ProductIndex(oi.company)
    built = time.perf_counter() - started
    started = time.perf_counter()
    for hint in ("generic item 04321 pack", "sugar", "basmati rice", "toor dal", "zzzz unknown thing"):
        index.resolve(hint)
    resolved = time.perf_counter() - started
    assert len(index.rows) >= 5000
    assert built < 3.0 and resolved < 8.0, (built, resolved)


def test_a_50_line_order_draft_uses_a_bounded_number_of_queries(oi):
    products = [make_product(oi.company, name=f"Spice {i}", sku=f"SP{i}", selling_price="10") for i in range(50)]
    text = "From: Sharma Traders\n" + "\n".join(f"{i + 1} spice {i}" for i in range(50))
    run = services.create_run(company=oi.company, agent_kind="ORDER_INTAKE", trigger=Trigger.USER, trigger_ref="TEXT:perf", user=oi.owner)
    with CaptureQueriesContext(connection) as ctx:
        done = runner.execute_run(run.pk, {"text": text})
    p = AgentProposal.objects.get(run=done)
    assert len(p.payload["lines"]) == 50 and all(l["product_id"] for l in p.payload["lines"])
    assert len(ctx) <= 6 * 50 + 60, f"{len(ctx)} queries for 50 lines"
    assert products


def test_an_inventory_sweep_over_200_low_items_stays_within_a_query_budget(iv):
    items = Product.objects.bulk_create([
        Product(company=iv.company, name=f"Low {i}", sku=f"LW{i}", selling_price=Decimal("10"), gst_rate=Decimal("5"), reorder_level=Decimal("10"))
        for i in range(200)
    ])
    for p in items[:200]:
        stock(iv, p, iv.main, "1")
    run = services.create_run(company=iv.company, agent_kind="INVENTORY_RISK", trigger=Trigger.SCHEDULE, trigger_ref="sweep:perf", user=iv.owner)
    started = time.perf_counter()
    with CaptureQueriesContext(connection) as ctx:
        done = runner.execute_run(run.pk)
    elapsed = time.perf_counter() - started
    assert done.status == "SUCCEEDED"
    lines = sum(len(p.payload["lines"]) for p in AgentProposal.objects.filter(run=done))
    assert lines >= 150, lines
    assert len(ctx) <= 12 * 200 + 100 and elapsed < 60, (len(ctx), elapsed)


def test_a_bill_sweep_over_60_draft_bills_stays_within_a_query_budget(bc):
    bills = PurchaseInvoice.objects.bulk_create([
        PurchaseInvoice(company=bc.company, supplier=bc.supplier, supplier_bill_number=f"PERF{i}", created_by=bc.owner, updated_by=bc.owner)
        for i in range(60)
    ])
    PurchaseItem.objects.bulk_create([
        PurchaseItem(company=bc.company, invoice=b, product=bc.widget, quantity=Decimal("1"), unit_price=Decimal("10"), gst_rate=Decimal("0"))
        for b in bills
    ])
    run = services.create_run(company=bc.company, agent_kind="BILL_CHECK", trigger=Trigger.SCHEDULE, trigger_ref="sweep:perf", user=bc.owner)
    with CaptureQueriesContext(connection) as ctx:
        done = runner.execute_run(run.pk)
    assert done.status == "SUCCEEDED"
    assert len(ctx) <= 20 * 60 + 50, f"{len(ctx)} queries for 60 bills"
