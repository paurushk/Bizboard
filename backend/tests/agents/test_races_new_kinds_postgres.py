# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)
"""Block F: concurrent approvals and pastes for the R3 to R5 proposal kinds. Skips unless the database is PostgreSQL."""

import json
import threading

import pytest
from django.db import connection

from agents import runner, services
from agents.enums import ProposalStatus, Trigger
from agents.models import AgentAlias, AgentProposal
from core.exceptions import BusinessRuleError
from inventory.models import StockTransfer
from purchases.models import PurchaseOrder
from sales.models import SalesOrder

from .conftest import owner_cu
from .test_inventory_risk import iv, short_item, sweep  # noqa: F401
from .test_order_intake import TEXT, oi, paste, proposal_of  # noqa: F401
from .test_races_postgres import _race

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _approve(t, p):
    return lambda: services.approve_proposal(company=t.company, company_user=owner_cu(t), proposal_id=p.pk, revision=p.revision).pk


def _only_one_won(results):
    oks = [r for r in results if r[0] == "ok"]
    others = [r for r in results if r[0] != "ok"]
    assert len(oks) == 1, results
    assert others and others[0][0] == "conflict" and others[0][1] == "AGT_E_BAD_TRANSITION", results


def test_two_simultaneous_approvals_of_an_order_draft_make_one_order_and_one_alias(oi):
    _require_postgres()
    p = proposal_of(paste(oi, "From: Sharma ji\n3 chini"))
    payload = json.loads(json.dumps(p.payload))
    payload.update(customer_id=oi.customer.id, customer_name=oi.customer.name)
    payload["lines"][0].update(product_id=oi.sugar.id, product_name=oi.sugar.name)
    p = services.edit_proposal(company=oi.company, company_user=owner_cu(oi), proposal_id=p.pk, edited_payload=payload, revision=p.revision)
    _only_one_won(_race(_approve(oi, p)))
    assert SalesOrder.objects.filter(company=oi.company).count() == 1
    assert AgentAlias.objects.filter(company=oi.company, raw_text_norm="chini").count() == 1
    assert AgentAlias.objects.get(raw_text_norm="chini").hits == 1


def test_two_simultaneous_approvals_of_a_transfer_draft_make_one_transfer(iv):
    _require_postgres()
    short_item(iv)
    p = AgentProposal.objects.get(run=sweep(iv), kind="STOCK_TRANSFER")
    _only_one_won(_race(_approve(iv, p)))
    assert StockTransfer.objects.filter(company=iv.company).count() == 1


def test_two_simultaneous_approvals_of_a_purchase_draft_make_one_order(iv):
    _require_postgres()
    short_item(iv)
    p = AgentProposal.objects.get(run=sweep(iv), kind="PURCHASE_REQUEST")
    _only_one_won(_race(_approve(iv, p)))
    assert PurchaseOrder.objects.filter(company=iv.company).count() == 1


def test_two_simultaneous_pastes_of_the_same_text_make_one_draft(oi):
    _require_postgres()

    def paste_once():
        run = services.create_run(company=oi.company, agent_kind="ORDER_INTAKE", trigger=Trigger.USER, trigger_ref="TEXT:race", user=oi.owner)
        done = runner.execute_run(run.pk, {"text": TEXT})
        return getattr(done, "proposal_ids_out", [None])[0] if done else None

    results = _race(paste_once)
    assert not [r for r in results if r[0] == "error"], results
    assert AgentProposal.objects.filter(company=oi.company, kind="SALES_ORDER_DRAFT").count() == 1


def test_an_edit_racing_an_approve_never_creates_an_order_from_a_stale_revision(oi):
    _require_postgres()
    p = proposal_of(paste(oi))
    payload = json.loads(json.dumps(p.payload))
    payload["lines"][0]["qty"] = "9"
    cu = owner_cu(oi)
    barrier, out = threading.Barrier(2, timeout=10), {}

    def edit():
        connection.close()
        try:
            barrier.wait()
            services.edit_proposal(company=oi.company, company_user=cu, proposal_id=p.pk, edited_payload=payload, revision=0)
            out["edit"] = "ok"
        except BusinessRuleError as exc:
            out["edit"] = exc.get_codes()
        finally:
            connection.close()

    def approve():
        connection.close()
        try:
            barrier.wait()
            services.approve_proposal(company=oi.company, company_user=cu, proposal_id=p.pk, revision=0)
            out["approve"] = "ok"
        except BusinessRuleError as exc:
            out["approve"] = exc.get_codes()
        finally:
            connection.close()

    threads = [threading.Thread(target=edit), threading.Thread(target=approve)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    p.refresh_from_db()
    orders = SalesOrder.objects.filter(company=oi.company)
    if out["approve"] == "ok":
        # approval won: the order has the original quantities and the late edit was refused
        assert out["edit"] != "ok" and p.status == ProposalStatus.EXECUTED
        assert [str(i.quantity) for i in orders.get().items.all()][0] != "9.000"
    else:
        # edit won: the approval carried a stale revision and was refused; nothing was created
        assert out["edit"] == "ok" and out["approve"] == "AGT_E_REVISION" and not orders.exists()
