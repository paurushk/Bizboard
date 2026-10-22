"""WP-I1: one spend counter in front of every model call; caps cannot be overshot."""

from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings

from core.services import ai_spend
from core.services.ai_spend import AiSpendBlocked


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


@override_settings(AI_TENANT_DAILY_TOKEN_CAP=10, AI_PLATFORM_DAILY_TOKEN_CAP=0)
def test_reservations_cannot_overshoot_the_company_cap():
    allowed = []

    def one():
        with ai_spend.charging(1):
            try:
                ai_spend.reserve(1)
                return True
            except AiSpendBlocked:
                return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = list(pool.map(lambda _i: one(), range(20)))
    assert sum(allowed) == 10
    assert ai_spend.used_today(1) == 10


@override_settings(AI_TENANT_DAILY_TOKEN_CAP=0, AI_PLATFORM_DAILY_TOKEN_CAP=100)
def test_the_platform_cap_covers_every_company_and_the_platform_itself():
    with ai_spend.charging(1):
        ai_spend.reserve(60)
    with ai_spend.charging(2):
        with pytest.raises(AiSpendBlocked, match="the platform"):
            ai_spend.reserve(60)
    ai_spend.reserve(40)  # ops copilot: no company, platform counter only
    assert ai_spend.used_today(None) == 100


@override_settings(AI_TENANT_DAILY_TOKEN_CAP=1000, AI_PLATFORM_DAILY_TOKEN_CAP=0)
def test_settle_replaces_the_estimate_with_real_usage():
    with ai_spend.charging(5):
        with ai_spend.guarded(800) as res:
            res.actual = 120
    assert ai_spend.used_today(5) == 120


@override_settings(AI_GLOBAL_KILL=True)
def test_the_global_kill_switch_refuses_every_call():
    with pytest.raises(AiSpendBlocked):
        ai_spend.reserve(1)
    assert not ai_spend.would_allow(1)


@override_settings(AI_SPEND_FAIL_CLOSED=True)
def test_counters_down_means_refuse():
    with mock.patch.object(ai_spend, "_incr", side_effect=ConnectionError("redis down")):
        with pytest.raises(AiSpendBlocked, match="unavailable"):
            ai_spend.reserve(1)


@override_settings(AI_TENANT_DAILY_TOKEN_CAP=5000, AI_PLATFORM_DAILY_TOKEN_CAP=0, LLM_PROVIDER="fake")
def test_every_call_path_is_counted():
    """The agents gateway, the assistant/ops chat and bill extraction all reserve."""
    from core.services import llm, llm_gateway

    reserved = []
    real = ai_spend.reserve

    def spy(estimate):
        reserved.append(estimate)
        return real(estimate)

    with mock.patch.object(ai_spend, "reserve", side_effect=spy):
        with ai_spend.charging(9):
            with mock.patch.object(llm_gateway, "_chat", return_value=llm_gateway.result_from_dict({"tokens_in": 3, "tokens_out": 4})):
                llm_gateway.chat(messages=[{"role": "user", "content": "hi"}])
            with mock.patch.object(llm, "_chat_with_tools", return_value={"usage": {"tokens_in": 1, "tokens_out": 2}}):
                llm.chat_with_tools(messages=[{"role": "user", "content": "hi"}])
            with mock.patch.object(llm, "_extract_openai_compatible", return_value=({"lines": []}, "stop")), \
                    mock.patch.object(llm, "_provider", return_value="openai"):
                try:
                    llm.extract_purchase_bill([b"\x89PNG fake"])
                except Exception:  # noqa: BLE001 - only the reservation matters here
                    pass
    assert len(reserved) >= 3
    assert ai_spend.used_today(9) > 0


@pytest.mark.django_db
@override_settings(AI_TENANT_DAILY_TOKEN_CAP=1, AI_PLATFORM_DAILY_TOKEN_CAP=0)
def test_agents_degrade_to_rules_only_when_today_is_spent(tenant_a):
    from agents import policy

    company = tenant_a.company
    company.ai_features_enabled = True
    with ai_spend.charging(company.pk):
        ai_spend.reserve(1)
    decision = policy.llm_decision(company)
    assert decision.allow_llm is False
