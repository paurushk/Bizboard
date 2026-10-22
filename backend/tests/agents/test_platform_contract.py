"""Platform-level contracts: the spec test every agent must pass, import boundaries, flags, RLS, backup."""

import ast
import pathlib

import pytest
from django.conf import settings

from agents import registry, spec
from agents.catalog import _example  # noqa: F401  (registers the example tool)

BACKEND = pathlib.Path(__file__).resolve().parents[2]


def _all_specs():
    import agents.catalog._example as ex

    return [ex.AGENT]


def check_contract(agent):
    """The checks every agent must pass. A new agent that passes is safe to merge behind its flag."""
    from agents.prompts import prompt_exists

    assert agent.flag.startswith("AGENT_")
    assert agent.prepare_permission is not None
    assert agent.title_key
    for name in agent.tools:
        assert name in registry.REGISTRY and registry.REGISTRY[name].money is False
        assert registry.export_json_schema(name)["function"]["name"] == name
    for pk in agent.proposal_kinds:
        assert pk.renderer in spec.RENDERERS
        assert pk.approve_permission is not None
        assert pk.payload_serializers and all(callable(s) for s in pk.payload_serializers.values())
        assert pk.default_ttl_hours > 0
        assert pk.autonomy <= 2, "L3 is reserved for approved reminders (R6)"
    for prompt in agent.prompt_names:
        assert prompt_exists(agent.package, prompt), f"missing prompt {prompt}"
    for fn in (agent.context_builder, agent.parse_final, agent.validate, agent.rules_only):
        assert callable(fn)
    for code in agent.attention_codes:
        from insights.attention import KNOWN_CODES
        from insights.event_schema import EVENT_SOURCES

        assert code in KNOWN_CODES and code in EVENT_SOURCES, f"{code} must be registered in attention (3.10)"
        assert code in (BACKEND.parent / "docs" / "ATTENTION_DEDUPE_KEYS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("agent", _all_specs(), ids=lambda a: a.kind)
def test_spec_contract(agent):
    check_contract(agent)


def test_every_agent_found_in_the_catalog_passes_the_contract():
    """Whatever autodiscover registers from agents/catalog (Collections today) must satisfy the same checks."""
    spec.autodiscover()
    found = [a for kind, a in spec.AGENTS.items() if kind != "EXAMPLE"]
    assert found, "autodiscover found no real agents"
    for agent in found:
        check_contract(agent)
        assert agent.package, f"{agent.kind} has no catalog package"


def test_atomic_requests_stays_off():
    """Approve relies on writing FAILED in a separate transaction after the executor rolls back."""
    for db in settings.DATABASES.values():
        assert not db.get("ATOMIC_REQUESTS")


def test_no_existing_app_imports_agents_except_the_allowed_places():
    allowed: set[str] = set()  # nothing outside agents/ imports it; URLs and Celery use dotted strings
    offenders = []
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith(("agents/", "tests/", ".venv/", "node_modules/", "media/")) or "/migrations/" in rel:
            continue
        if rel in allowed:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n == "agents" or n.startswith("agents.") for n in names):
                offenders.append(rel)
    assert not offenders, f"These apps must not import agents (ADR-A5): {sorted(set(offenders))}"


def test_agent_flags_default_off_and_prefix_is_recognised(db):
    from core.services.feature_flags import build_feature_flags
    from tests.conftest import make_tenant

    t = make_tenant("flags1")
    flags = build_feature_flags(company=t.company)
    assert flags["ENABLE_AGENTS"] is False and not any(k.startswith("AGENT_") and v for k, v in flags.items())
    t.company.feature_flags = {"ENABLE_AGENTS": True, "AGENT_ANYTHING": True, "AGENT_OFF": False, "NOT_AGENT": True}
    t.company.save()
    flags = build_feature_flags(company=t.company)
    assert flags["ENABLE_AGENTS"] and flags["AGENT_ANYTHING"] and flags["AGENT_OFF"] is False
    assert "NOT_AGENT" not in flags


def test_agent_tables_are_in_the_rls_migration():
    from core.migrations import __path__ as _  # noqa: F401
    import importlib

    mod = importlib.import_module("core.migrations.0066_rls_agents_tables")
    assert set(mod.RLS_TABLES) == {"agents_agentrun", "agents_agentstep", "agents_agentproposal", "agents_agentalias"}


def test_ai_usage_ledger_has_one_agent_feature_and_a_kind_column():
    from insights.models import AiUsageLedger

    assert AiUsageLedger.Feature.AGENT == "AGENT"
    assert AiUsageLedger._meta.get_field("agent_kind").max_length == 48


def test_agent_transient_codes_are_registered_with_idempotency():
    from agents.error_codes import TRANSIENT_CODES
    from core.idempotency import TRANSIENT_4XX_CODES

    assert TRANSIENT_CODES <= set(TRANSIENT_4XX_CODES)


def test_agent_idempotency_scopes_are_not_money_scopes():
    from agents import views
    from core.idempotency import MONEY_IDEMPOTENCY_SCOPES

    for scope in (views.SCOPE_RUN_START, views.SCOPE_APPROVE, views.SCOPE_BULK_APPROVE):
        assert scope not in MONEY_IDEMPOTENCY_SCOPES


@pytest.mark.django_db
def test_tenant_backup_round_trips_agent_rows(example_agent):
    from accounts import agents_backup
    from agents.models import AgentAlias, AgentProposal, AgentRun
    from tests.agents.conftest import enable_agents, make_proposal
    from tests.conftest import make_customer, make_tenant

    t = make_tenant("bk1")
    enable_agents(t.company, "AGENT_EXAMPLE")
    make_proposal(t)
    cust = make_customer(t.company)
    AgentAlias.objects.create(company=t.company, scope="CUSTOMER", raw_text_norm="ravi", customer=cust)

    extra = {}
    from accounts.tenant_backup import _optional_rows

    agents_backup.export_rows(t.company, extra, _optional_rows)
    assert len(extra["agent_runs"]) == 1 and len(extra["agent_proposals"]) == 1 and len(extra["agent_aliases"]) == 1

    agents_backup.wipe(t.company)
    assert not AgentRun.objects.filter(company=t.company).exists()
    assert not AgentProposal.objects.filter(company=t.company).exists()
    assert not AgentAlias.objects.filter(company=t.company).exists()


@pytest.mark.django_db
def test_export_then_sandbox_restore_keeps_agent_rows_and_remaps_ids(example_agent):
    """The whole backup path, not just the helper: runs, proposals and aliases survive and point at the new rows."""
    import base64

    from accounts.models import Company
    from agents.models import AgentAlias, AgentProposal, AgentRun
    from tests.agents.conftest import enable_agents, make_proposal
    from tests.conftest import make_customer, make_tenant

    t = make_tenant("bk2")
    enable_agents(t.company, "AGENT_EXAMPLE")
    p = make_proposal(t)
    cust = make_customer(t.company, name="Alias Target")
    AgentAlias.objects.create(company=t.company, scope="CUSTOMER", raw_text_norm="alias target", customer=cust, hits=3)

    export = t.client.post("/api/v1/company/export/")
    assert export.status_code == 200
    restore = t.client.post("/api/v1/company/restore/", {"payload": base64.b64encode(export.content).decode("ascii")}, format="json")
    assert restore.status_code == 201, restore.data
    sandbox = Company.objects.get(pk=restore.data["company_id"])

    assert AgentRun.objects.filter(company=sandbox).count() == 1
    [sp] = AgentProposal.objects.filter(company=sandbox)
    assert sp.run.company_id == sandbox.id and sp.payload == p.payload and sp.kind == p.kind
    [alias] = AgentAlias.objects.filter(company=sandbox)
    assert alias.customer.company_id == sandbox.id and alias.customer.name == "Alias Target" and alias.hits == 3
    # The source tenant is untouched.
    assert AgentProposal.objects.filter(company=t.company).count() == 1
