"""OpenAI / DeepSeek adapter: assistant tool_calls + one role=tool message per call id."""

from __future__ import annotations

import json

from django.conf import settings

from core.exceptions import BusinessRuleError
from core.services.llm_gateway import LlmProviderError, LlmResult, ToolCall


def to_provider_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "assistant" and m.get("tool_calls"):
            out.append({
                "role": "assistant",
                "content": m.get("content") or None,
                "tool_calls": [
                    {
                        "id": str(tc["id"]),
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments") or {})},
                    }
                    for tc in m["tool_calls"]
                ],
            })
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": str(m["tool_call_id"]), "content": m.get("content", "")})
        else:
            out.append({"role": role, "content": m.get("content", "")})
    return out


def chat(*, provider, model, messages, tools, max_tokens, timeout) -> LlmResult:
    key = getattr(settings, "OPENAI_API_KEY" if provider == "openai" else "DEEPSEEK_API_KEY", "") or ""
    if not key:
        raise BusinessRuleError("LLM API key is not configured.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise BusinessRuleError("openai package is not installed.") from exc
    base_url = None if provider == "openai" else (getattr(settings, "DEEPSEEK_BASE_URL", None) or "https://api.deepseek.com")
    client = OpenAI(api_key=key, base_url=base_url, timeout=timeout) if base_url else OpenAI(api_key=key, timeout=timeout)
    kwargs = {"model": model, "messages": to_provider_messages(messages), "temperature": 0, "max_tokens": max_tokens}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 - classify provider errors for the runner's retry rule
        status = getattr(exc, "status_code", None)
        transient = status is None or status == 429 or status >= 500
        raise LlmProviderError(str(exc), transient=transient) from exc
    choice = response.choices[0]
    msg = choice.message
    calls = []
    for tc in getattr(msg, "tool_calls", None) or []:
        raw = tc.function.arguments if tc.function else "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=tc.id, name=tc.function.name if tc.function else "", arguments=args if isinstance(args, dict) else {}))
    usage = getattr(response, "usage", None)
    return LlmResult(
        text=msg.content or "",
        tool_calls=calls,
        tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
        tokens_out=getattr(usage, "completion_tokens", 0) or 0,
        model=model,
        finish_reason=getattr(choice, "finish_reason", "") or "",
    )
