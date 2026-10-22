"""Anthropic adapter: assistant tool_use blocks, then a user message of tool_result blocks by tool_use_id."""

from __future__ import annotations

from django.conf import settings

from core.exceptions import BusinessRuleError
from core.services.llm_gateway import LlmProviderError, LlmResult, ToolCall


def to_provider_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    out: list[dict] = []
    pending_results: list[dict] = []

    def flush():
        nonlocal pending_results
        if pending_results:
            out.append({"role": "user", "content": pending_results})
            pending_results = []

    for m in messages:
        role = m["role"]
        if role == "system":
            continue
        if role == "tool":
            pending_results.append({
                "type": "tool_result",
                "tool_use_id": str(m["tool_call_id"]),
                "content": m.get("content", ""),
            })
            continue
        flush()
        if role == "assistant" and m.get("tool_calls"):
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                blocks.append({"type": "tool_use", "id": str(tc["id"]), "name": tc["name"], "input": tc.get("arguments") or {}})
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": role, "content": m.get("content", "")})
    flush()
    return system, out


def _anthropic_tools(tools: list[dict]) -> list[dict]:
    res = []
    for t in tools:
        fn = t.get("function") or {}
        res.append({
            "name": fn.get("name") or t.get("name"),
            "description": fn.get("description") or "",
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return res


def chat(*, model, messages, tools, max_tokens, timeout) -> LlmResult:
    key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    if not key:
        raise BusinessRuleError("ANTHROPIC_API_KEY is not configured.")
    try:
        import anthropic
    except ImportError as exc:
        raise BusinessRuleError("anthropic package is not installed.") from exc
    client = anthropic.Anthropic(api_key=key, timeout=timeout)
    system, msgs = to_provider_messages(messages)
    kwargs = {"model": model, "max_tokens": max_tokens, "temperature": 0, "messages": msgs}
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = _anthropic_tools(tools)
    try:
        response = client.messages.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        transient = status is None or status == 429 or status >= 500
        raise LlmProviderError(str(exc), transient=transient) from exc
    text, calls = "", []
    for block in response.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text += block.text or ""
        elif btype == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input if isinstance(block.input, dict) else {}))
    return LlmResult(
        text=text,
        tool_calls=calls,
        tokens_in=getattr(response.usage, "input_tokens", 0) or 0,
        tokens_out=getattr(response.usage, "output_tokens", 0) or 0,
        model=model,
        finish_reason=getattr(response, "stop_reason", "") or "",
    )
