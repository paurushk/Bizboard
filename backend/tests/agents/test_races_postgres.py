"""Concurrent approve and run-start races. SQLite cannot show a row-lock bug, so these skip unless the database is
PostgreSQL (CI with DATABASE_URL), like tests/test_concurrency_races.py."""

from __future__ import annotations

import threading

import pytest
from django.db import connection

from agents import services
from agents.enums import ProposalStatus
from agents.models import AgentProposal, AgentRun
from core.exceptions import BusinessRuleError

from .conftest import make_proposal, owner_cu

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _race(fn, n=2):
    results, barrier = [], threading.Barrier(n, timeout=10)

    def worker():
        connection.close()
        try:
            barrier.wait()
            results.append(("ok", fn()))
        except BusinessRuleError as exc:
            results.append(("conflict", exc.get_codes()))
        except Exception as exc:  # pragma: no cover - unexpected
            results.append(("error", repr(exc)))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_two_simultaneous_approves_execute_once(tenant):
    _require_postgres()
    p = make_proposal(tenant)
    cu = owner_cu(tenant)
    results = _race(lambda: services.approve_proposal(company=tenant.company, company_user=cu, proposal_id=p.pk, revision=0))
    assert [r[0] for r in results].count("ok") == 1, results
    assert [r for r in results if r[0] != "ok"][0][1] == "AGT_E_BAD_TRANSITION"
    p.refresh_from_db()
    assert p.status == ProposalStatus.EXECUTED and p.attempts == 1


def test_two_simultaneous_edits_one_wins_the_revision(tenant):
    _require_postgres()
    p = make_proposal(tenant)
    cu = owner_cu(tenant)
    results = _race(lambda: services.edit_proposal(
        company=tenant.company, company_user=cu, proposal_id=p.pk, edited_payload={"text": "same 3 items"}, revision=0,
    ))
    assert [r[0] for r in results].count("ok") == 1 and any(r == ("conflict", "AGT_E_REVISION") for r in results), results
    p.refresh_from_db()
    assert p.revision == 1


def test_two_simultaneous_run_starts_for_one_row_create_one_run(tenant):
    _require_postgres()
    results = _race(lambda: services.create_run(
        company=tenant.company, agent_kind="EXAMPLE", trigger="USER", trigger_ref="same-row", user=tenant.owner,
    ).pk)
    ids = {r[1] for r in results if r[0] == "ok"}
    assert len(ids) == 1, results
    assert AgentRun.objects.filter(company=tenant.company, trigger_ref="same-row").count() == 1


def test_two_simultaneous_drafts_for_one_key_create_one_proposal(tenant):
    _require_postgres()
    run_a = services.create_run(company=tenant.company, agent_kind="EXAMPLE", trigger="USER", trigger_ref="a", user=tenant.owner)
    run_b = services.create_run(company=tenant.company, agent_kind="EXAMPLE", trigger="USER", trigger_ref="b", user=tenant.owner)
    draft = {
        "kind": "EXAMPLE_NOTE", "title": "x", "dedupe_key": "race-key", "payload": {"text": "hello 3 items"},
        "evidence": [{"type": "fact", "id": "n", "label": "3 items", "fact": 3}],
    }
    runs = [run_a, run_b]
    idx = {"i": 0}
    lock = threading.Lock()

    def make():
        with lock:
            run = runs[idx["i"] % 2]
            idx["i"] += 1
        return services.create_proposals(run, [draft])[0].pk

    results = _race(make)
    assert len({r[1] for r in results if r[0] == "ok"}) == 1, results
    assert AgentProposal.objects.filter(company=tenant.company, dedupe_key="race-key").count() == 1
