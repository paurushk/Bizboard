import pytest

from agents import spec
from core.services.llm_providers import fake
from tests.conftest import make_tenant


@pytest.fixture(autouse=True)
def _fake_llm_reset(request):
    fake.reset()
    yield
    if not request.node.get_closest_marker("allows_raw_pii"):
        _assert_no_raw_pii_reached_the_model()
    fake.reset()


def _assert_no_raw_pii_reached_the_model():
    """WP-I1: every agent test doubles as a privacy test. Whatever the run sent to the model
    (user text, tool results, retries) must not hold a raw email, phone, GSTIN or PAN."""
    import json

    from agents import redaction

    patterns = {
        "email": redaction._EMAIL, "phone": redaction._PHONE,
        "gstin": redaction._GSTIN, "pan": redaction._PAN,
    }
    for call in fake.CALLS:
        for message in call["messages"]:
            if message.get("role") == "system":
                continue  # static prompt text, not customer data
            text = message.get("content")
            text = text if isinstance(text, str) else json.dumps(text, default=str)
            for kind, rx in patterns.items():
                hit = rx.search(text or "")
                assert hit is None, f"raw {kind} sent to the model in a {message.get('role')} message: {hit.group(0)!r}"


@pytest.fixture
def example_agent():
    """Register the inert example agent for one test, then remove it."""
    import agents.catalog._example as ex

    if "EXAMPLE" not in spec.AGENTS:
        spec.register(ex.AGENT)
    yield ex
    spec.unregister("EXAMPLE")


def enable_agents(company, *flags):
    company.feature_flags = {**(company.feature_flags or {}), "ENABLE_AGENTS": True, **{f: True for f in flags}}
    company.save(update_fields=["feature_flags"])
    return company


@pytest.fixture
def tenant(example_agent, db):
    t = make_tenant("agt1")
    enable_agents(t.company, "AGENT_EXAMPLE")
    return t


@pytest.fixture
def other_tenant(example_agent, db):
    t = make_tenant("agt2")
    enable_agents(t.company, "AGENT_EXAMPLE")
    return t


def owner_cu(tenant):
    return tenant.company.memberships.get(user=tenant.owner)


def staff_cu(tenant):
    return tenant.company.memberships.get(user=tenant.staff)


def make_run(tenant, **kw):
    from agents import services
    from agents.enums import Trigger

    return services.create_run(
        company=tenant.company, agent_kind=kw.pop("agent_kind", "EXAMPLE"),
        trigger=kw.pop("trigger", Trigger.USER), trigger_ref=kw.pop("trigger_ref", "r1"), user=kw.pop("user", tenant.owner),
    )


def make_proposal(tenant, *, text="hello 3 items", fail="", dedupe="k1", run=None):
    from agents import services

    run = run or make_run(tenant, trigger_ref=f"run-{dedupe}")
    [p] = services.create_proposals(run, [{
        "kind": "EXAMPLE_NOTE", "title": "Example", "dedupe_key": dedupe,
        "payload": {"text": text, "fail": fail},
        "evidence": [{"type": "fact", "id": "count", "label": "3 items", "fact": 3}],
    }])
    return p
