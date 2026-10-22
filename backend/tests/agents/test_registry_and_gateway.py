import pytest

from agents import registry
from agents.registry import ToolContext
from core.exceptions import BusinessRuleError
from core.services import llm_gateway
from core.services.llm_gateway import LlmProviderError
from core.services.llm_providers import claude, fake, openai_like


# --- registry ------------------------------------------------------------------------------------
def test_money_tools_cannot_be_registered():
    with pytest.raises(RuntimeError):
        registry.tool(name="pay_supplier", money=True)


def test_no_registered_tool_is_money(example_agent):
    assert all(not t.money for t in registry.REGISTRY.values())


def test_every_tool_schema_round_trips(example_agent):
    for name, tspec in registry.REGISTRY.items():
        schema = registry.export_json_schema(name)
        assert schema["function"]["name"] == name
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        if tspec.args is not None:
            assert set(params["properties"]) == {f for f, fld in tspec.args().fields.items() if not fld.read_only}


@pytest.mark.django_db
def test_invoke_strips_company_id_and_validates(tenant):
    ctx = ToolContext(company=tenant.company, company_user=None)
    out = registry.invoke("example_lookup", {"limit": 2, "company_id": 999}, ctx, allowlist=["example_lookup"])
    assert len(out["items"]) == 2
    with pytest.raises(BusinessRuleError):
        registry.invoke("example_lookup", {"limit": 500}, ctx, allowlist=["example_lookup"])


@pytest.mark.django_db
def test_invoke_enforces_allowlist_and_role(tenant):
    from .conftest import staff_cu

    ctx = ToolContext(company=tenant.company, company_user=staff_cu(tenant))
    with pytest.raises(BusinessRuleError):
        registry.invoke("example_lookup", {}, ctx, allowlist=[])
    with pytest.raises(BusinessRuleError):
        registry.invoke("example_lookup", {}, ctx, allowlist=["example_lookup"])  # staff cannot see reports
    with pytest.raises(BusinessRuleError):
        registry.invoke("nope", {}, ctx, allowlist=["nope"])


def test_result_rows_are_capped():
    out = registry._cap_rows({"rows": list(range(100))}, 10)
    assert len(out["rows"]) == 10 and out["rows_truncated"] is True


# --- gateway: tool message protocol --------------------------------------------------------------
MSGS = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "t", "arguments": {"a": 1}}]},
    {"role": "tool", "tool_call_id": "c1", "name": "t", "content": "{}"},
]


def test_validate_messages_rejects_unmatched_tool_result():
    llm_gateway.validate_messages(MSGS)
    bad = MSGS[:3] + [{"role": "tool", "tool_call_id": "zzz", "name": "t", "content": "{}"}]
    with pytest.raises(BusinessRuleError):
        llm_gateway.validate_messages(bad)
    with pytest.raises(BusinessRuleError):
        llm_gateway.validate_messages([{"role": "tool", "tool_call_id": "c1", "content": "x"}])
    with pytest.raises(BusinessRuleError):
        llm_gateway.validate_messages([{"role": "robot", "content": "x"}])


def test_openai_translation_correlates_ids():
    out = openai_like.to_provider_messages(MSGS)
    assert out[2]["tool_calls"][0]["id"] == "c1" and out[2]["tool_calls"][0]["type"] == "function"
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "{}"}


def test_claude_translation_uses_tool_use_blocks_and_batches_results():
    two = [
        MSGS[0], MSGS[1],
        {"role": "assistant", "content": "x", "tool_calls": [{"id": "c1", "name": "t", "arguments": {}}, {"id": "c2", "name": "t", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "t", "content": "r1"},
        {"role": "tool", "tool_call_id": "c2", "name": "t", "content": "r2"},
    ]
    system, out = claude.to_provider_messages(two)
    assert system == "sys"
    assert [b["type"] for b in out[1]["content"]] == ["text", "tool_use", "tool_use"]
    assert out[2]["role"] == "user" and [b["tool_use_id"] for b in out[2]["content"]] == ["c1", "c2"]


# --- fake provider -------------------------------------------------------------------------------
def test_fake_provider_is_keyed_by_step_and_fails_loudly():
    fake.script("A", step=1, response={"tool_calls": [{"id": "c1", "name": "t", "arguments": {}}]})
    fake.script("A", step=2, response={"text": "done", "tokens_in": 5, "tokens_out": 2})
    r1 = llm_gateway.chat(messages=[{"role": "user", "content": "x"}], meta={"agent": "A", "step_seq": 1})
    r2 = llm_gateway.chat(messages=[{"role": "user", "content": "x"}], meta={"agent": "A", "step_seq": 2})
    assert r1.tool_calls[0].id == "c1" and r2.text == "done" and r2.tokens_in == 5
    with pytest.raises(BusinessRuleError, match="No fake LLM script"):
        llm_gateway.chat(messages=[{"role": "user", "content": "x"}], meta={"agent": "A", "step_seq": 3})


def test_fake_provider_can_raise_provider_errors():
    fake.script("B", step=1, response=LlmProviderError("boom"))
    with pytest.raises(LlmProviderError):
        llm_gateway.chat(messages=[{"role": "user", "content": "x"}], meta={"agent": "B", "step_seq": 1})


def test_gateway_uses_fake_in_tests():
    assert llm_gateway.provider_name() == "fake"
