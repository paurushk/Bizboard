"""Provider-neutral chat + tool calling for agents (AGT-103).

Neutral message shape (a list of dicts):
  {"role": "system", "content": str}
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "arguments"}]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}

Each adapter translates this faithfully. The existing core.services.llm.chat_with_tools is NOT used
for agents: it drops tool_use / tool_result blocks for Claude, so a multi-step tool loop would fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from core.exceptions import BusinessRuleError

ROLES = {"system", "user", "assistant", "tool"}


class LlmProviderError(Exception):
    """Transport-level failure (timeout, 429, 5xx). The runner may retry these."""

    def __init__(self, message: str, *, transient: bool = True):
        super().__init__(message)
        self.transient = transient


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LlmResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    finish_reason: str = ""


def provider_name() -> str:
    name = (getattr(settings, "LLM_AGENT_PROVIDER", "") or getattr(settings, "LLM_PROVIDER", "") or "openai")
    return name.strip().lower()


def model_for(provider: str) -> str:
    override = (getattr(settings, "LLM_AGENT_MODEL", "") or getattr(settings, "LLM_MODEL", "") or "").strip()
    if override:
        return override
    from core.services.llm import DEFAULT_MODELS

    return DEFAULT_MODELS.get(provider, "")


def validate_messages(messages: list[dict]) -> None:
    """Fail before the network: every tool message must answer a prior assistant tool call id."""
    open_ids: set[str] = set()
    for i, m in enumerate(messages):
        role = m.get("role")
        if role not in ROLES:
            raise BusinessRuleError(f"Bad message role at {i}: {role!r}")
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                open_ids.add(str(tc["id"]))
        elif role == "tool":
            tid = str(m.get("tool_call_id") or "")
            if tid not in open_ids:
                raise BusinessRuleError(f"Tool result at {i} does not match a prior tool call id ({tid!r}).")
            open_ids.discard(tid)


def chat(
    *,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 1024,
    timeout: float = 30.0,
    meta: dict | None = None,
) -> LlmResult:
    """One model turn. ``meta`` carries (agent, prompt_version, input_digest, step_seq) for the fake provider."""
    validate_messages(messages)
    from core.services import ai_spend

    # WP-I1: reserve before the call so concurrent runs cannot overshoot a daily cap.
    estimate = max_tokens + sum(len(str(m.get("content") or "")) for m in messages) // 4
    with ai_spend.guarded(estimate) as res:
        result = _chat(messages=messages, tools=tools, max_tokens=max_tokens, timeout=timeout, meta=meta)
        res.actual = int(result.tokens_in) + int(result.tokens_out)
    return result


def _chat(*, messages, tools, max_tokens, timeout, meta) -> LlmResult:
    provider = provider_name()
    model = model_for(provider)
    if provider == "fake":
        from core.services.llm_providers import fake

        return fake.chat(messages=messages, tools=tools or [], meta=meta or {})
    if provider in ("openai", "deepseek"):
        from core.services.llm_providers import openai_like

        return openai_like.chat(
            provider=provider, model=model, messages=messages, tools=tools or [],
            max_tokens=max_tokens, timeout=timeout,
        )
    if provider == "claude":
        from core.services.llm_providers import claude

        return claude.chat(
            model=model, messages=messages, tools=tools or [], max_tokens=max_tokens, timeout=timeout,
        )
    raise BusinessRuleError(f"Unsupported LLM provider '{provider}'.")


def result_from_dict(d: dict[str, Any]) -> LlmResult:
    return LlmResult(
        text=d.get("text", ""),
        tool_calls=[ToolCall(id=str(t["id"]), name=t["name"], arguments=t.get("arguments") or {}) for t in d.get("tool_calls", [])],
        tokens_in=int(d.get("tokens_in", 0)),
        tokens_out=int(d.get("tokens_out", 0)),
        model=d.get("model", "fake"),
        finish_reason=d.get("finish_reason", "stop"),
    )
