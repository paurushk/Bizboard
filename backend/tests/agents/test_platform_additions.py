"""Block E of the test plan: the paste-text contract, linked drafts and what the real agents declare."""
# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)

import dataclasses
import uuid

import pytest

from agents import services, spec
from agents.models import AgentProposal
from agents.spec import SpecError

from .conftest import enable_agents, example_agent, make_run, tenant  # noqa: F401
from .test_order_intake import oi, paste, proposal_of  # noqa: F401

pytestmark = pytest.mark.django_db
BASE = "/api/v1/agents"


def key():
    return {"HTTP_IDEMPOTENCY_KEY": f"k-{uuid.uuid4()}"}


def d(resp):
    return resp.json()["data"]


@pytest.fixture
def text_agent(example_agent):  # noqa: F811
    ex = example_agent
    kind = dataclasses.replace(ex.NOTE, kind="EXAMPLE_TEXT_NOTE")
    agent = dataclasses.replace(
        ex.AGENT, kind="EXAMPLE_TEXT", flag="AGENT_EXAMPLE_TEXT", proposal_kinds=[kind], tools=[], schedule=None,
        accepts_text=True, text_max_chars=20,
        rules_only=lambda tctx, context: [{**x, "kind": "EXAMPLE_TEXT_NOTE"} for x in ex._rules_only(tctx, context)],
    )
    spec.register(agent)
    yield agent
    spec.unregister("EXAMPLE_TEXT")


def test_a_text_agent_cannot_declare_a_schedule(example_agent):  # noqa: F811
    bad = dataclasses.replace(
        example_agent.AGENT, kind="EXAMPLE_BAD", flag="AGENT_EXAMPLE_BAD",
        proposal_kinds=[dataclasses.replace(example_agent.NOTE, kind="EXAMPLE_BAD_NOTE")], tools=[],
        accepts_text=True, schedule={"hour": 8, "minute": 0},
    )
    with pytest.raises(SpecError):
        spec.register(bad)
    assert "EXAMPLE_BAD" not in spec.AGENTS and "EXAMPLE_BAD_NOTE" not in spec.PROPOSAL_KINDS


def test_the_text_limit_is_the_specs_own(tenant, text_agent):  # noqa: F811
    enable_agents(tenant.company, "AGENT_EXAMPLE_TEXT")
    over = tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE_TEXT", "text": "x" * 21}, format="json", **key())
    exact = tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE_TEXT", "text": "x" * 20}, format="json", **key())
    assert over.status_code == 400 and exact.status_code == 200


def test_a_text_agent_requires_text_and_other_agents_refuse_it(tenant, text_agent):  # noqa: F811
    enable_agents(tenant.company, "AGENT_EXAMPLE_TEXT")
    assert tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE_TEXT", "text": "   "}, format="json", **key()).status_code == 400
    assert tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE", "text": "hello"}, format="json", **key()).status_code == 400


def test_a_repeated_paste_returns_the_existing_live_draft_id(tenant, text_agent):  # noqa: F811
    enable_agents(tenant.company, "AGENT_EXAMPLE_TEXT")
    ids = []
    for _ in range(2):
        r = tenant.client.post(f"{BASE}/runs/", {"agent": "EXAMPLE_TEXT", "text": "same text"}, format="json", **key())
        ids.append(d(r))
    assert ids[0]["proposalIds"] == ids[1]["proposalIds"] and len(ids[0]["proposalIds"]) == 1


def test_proposals_can_be_filtered_by_group_key(tenant):
    run = make_run(tenant)
    drafts = [
        {"kind": "EXAMPLE_NOTE", "title": f"n{i}", "dedupe_key": f"k{i}", "group_key": group, "payload": {"text": "hello 3 items"},
         "evidence": [{"type": "fact", "id": "c", "label": "3 items", "fact": 3}]}
        for i, group in enumerate(["G1", "G1", "G2"])
    ]
    services.create_proposals(run, drafts)
    rows = d(tenant.client.get(f"{BASE}/proposals/", {"group_key": "G1"}))["results"]
    assert len(rows) == 2 and {r["groupKey"] for r in rows} == {"G1"}


def test_bulk_approve_refuses_order_drafts(oi):  # noqa: F811
    p = proposal_of(paste(oi))
    r = oi.client.post(f"{BASE}/proposals/bulk-approve/", {"items": [{"id": p.pk, "revision": p.revision}]}, format="json", **key())
    assert r.status_code == 200 and d(r)["results"][0]["ok"] is False
    p.refresh_from_db()
    assert p.status == "PENDING"


def test_every_real_agent_declares_a_complete_contract():
    from agents.spec import AGENTS, RENDERERS

    expected = {"COLLECTIONS", "ORDER_INTAKE", "INVENTORY_RISK", "BILL_CHECK"}
    assert expected <= set(AGENTS)
    for kind in expected:
        agent = AGENTS[kind]
        assert agent.flag == f"AGENT_{kind}" and agent.title_key.startswith("agents.")
        assert agent.prepare_permission is not None
        for pk in agent.proposal_kinds:
            assert pk.renderer in RENDERERS and pk.approve_permission is not None and pk.current_version in pk.payload_serializers
            assert pk.executor is not None and pk.title_key.startswith("agents.")
        if agent.accepts_text:
            assert agent.schedule is None and agent.text_max_chars > 0


def test_proposal_kind_names_are_unique_across_agents():
    from agents.spec import AGENTS

    names = [pk.kind for a in AGENTS.values() for pk in a.proposal_kinds]
    assert len(names) == len(set(names))
    assert AgentProposal is not None
