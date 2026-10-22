# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)
"""Block I: prove the evaluation sets can fail. Each test breaks one rule on purpose and expects the matching
evaluation to go red; if a set stays green under a broken rule, it is not measuring that rule."""

from decimal import Decimal

import pytest

from . import test_eval_order_intake as order_eval
from . import test_eval_sets as sets
from .test_eval_order_intake import world  # noqa: F401
from .test_eval_sets import bc, col, iv  # noqa: F401

pytestmark = pytest.mark.django_db


def test_order_eval_fails_when_every_fuzzy_match_is_accepted(world, monkeypatch):
    from agents.catalog.order_intake import resolver

    monkeypatch.setattr(resolver, "_score", lambda a, b: 1.0 if a and b else 0.0)
    with pytest.raises(AssertionError):
        order_eval.test_line_match_on_the_synthetic_set(world)


def test_order_eval_fails_when_matching_is_too_strict(world, monkeypatch):
    from agents.catalog.order_intake import resolver

    monkeypatch.setattr(resolver, "ACCEPT", 0.999)
    with pytest.raises(AssertionError):
        order_eval.test_line_match_on_the_synthetic_set(world)


def test_order_eval_fails_when_quantities_are_misread(world, monkeypatch):
    from agents.catalog.order_intake import parsing

    real = parsing._qty
    monkeypatch.setattr(parsing, "_qty", lambda token: real(str(int(float(token.replace(",", ".")) + 1))))
    with pytest.raises(AssertionError):
        order_eval.test_line_match_on_the_synthetic_set(world)


def test_bill_eval_fails_when_the_rate_tolerance_is_removed(bc, monkeypatch):
    monkeypatch.setattr("purchases.services._three_way_rate_tolerance", lambda reference: Decimal("0"))
    with pytest.raises(AssertionError):
        sets.test_bill_check_eval_matches_the_written_rules_and_the_existing_three_way_match(bc)


def test_bill_eval_fails_when_quantity_checks_are_skipped(bc, monkeypatch):
    monkeypatch.setattr("purchases.services._THREE_WAY_QTY_TOLERANCE", Decimal("1000"))
    with pytest.raises(AssertionError):
        sets.test_bill_check_eval_matches_the_written_rules_and_the_existing_three_way_match(bc)


def test_inventory_eval_fails_when_expired_lots_are_offered(iv, monkeypatch):
    from inventory.models import BatchLot
    from inventory.services import InventoryValuationService

    monkeypatch.setattr(
        InventoryValuationService, "fefo_batches",
        staticmethod(lambda company, product, warehouse=None: BatchLot.objects.filter(company=company, product=product).order_by("id")),
    )
    with pytest.raises(AssertionError):
        sets.test_inventory_eval_lots_never_expired_or_held(iv)


def test_inventory_eval_fails_when_quantities_drift_from_the_planning_rows(iv, monkeypatch):
    from agents.catalog.inventory_risk import context

    real = context._num
    monkeypatch.setattr(context, "_num", lambda value: real(Decimal(str(value)) + 1))
    with pytest.raises(AssertionError):
        sets.test_inventory_eval_quantities_equal_the_planning_output_and_never_exceed_the_donor(iv)


def test_collections_eval_fails_when_the_amount_in_the_text_is_wrong(col, monkeypatch):
    from agents.catalog.collections import context

    monkeypatch.setattr(context, "inr", lambda value: str(Decimal(str(value)) + 7))
    # Either the draft is refused (no proposal, so the case cannot even be unpacked) or its numbers are caught.
    with pytest.raises((AssertionError, ValueError)):
        sets.test_collections_eval_numbers_trace_to_the_ledger.__wrapped__(col, 12) if hasattr(
            sets.test_collections_eval_numbers_trace_to_the_ledger, "__wrapped__"
        ) else _run_collections_case(col)


def _run_collections_case(col):
    from .test_collections import overdue_invoice, run_for
    from agents import numbers
    from agents.catalog.collections import context as col_ctx
    from agents.models import AgentProposal
    from django.utils import timezone

    inv = overdue_invoice(col, days=12, name="Party12")
    run = run_for(col, f"AR_CUSTOMER:{inv.customer_id}")
    [p] = AgentProposal.objects.filter(run=run)
    facts = col_ctx.customer_facts(col.company, inv.customer, timezone.localdate())
    for variant in p.payload["variants"].values():
        assert not numbers.invented_numbers(variant, [facts, col.company.name], cited_count=len(p.evidence))
