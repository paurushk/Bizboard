"""Scripted provider for tests and dry runs. Never touches the network.

Scripts are keyed by (agent, prompt_version, input_digest, step_seq) with progressively looser
fallbacks, so a test can script one step without knowing the digest:

    fake.script("COLLECTIONS", step=1, response={...})          # any version / digest
    fake.script("COLLECTIONS", step=2, response={...}, digest="abc")

A missing script fails loudly and names the key it looked for.
"""

from __future__ import annotations

from core.exceptions import BusinessRuleError

_SCRIPTS: dict[tuple, object] = {}
CALLS: list[dict] = []


def reset() -> None:
    _SCRIPTS.clear()
    CALLS.clear()


def script(agent, *, step, response, version=None, digest=None):
    """``response`` is a dict (text/tool_calls/tokens_*), an Exception to raise, or a callable(messages)."""
    _SCRIPTS[(agent, version, digest, step)] = response


def _lookup(meta):
    agent, version, digest, step = meta.get("agent"), meta.get("prompt_version"), meta.get("input_digest"), meta.get("step_seq")
    for key in ((agent, version, digest, step), (agent, version, None, step), (agent, None, digest, step), (agent, None, None, step)):
        if key in _SCRIPTS:
            return _SCRIPTS[key]
    raise BusinessRuleError(f"No fake LLM script for agent={agent!r} version={version!r} digest={digest!r} step={step!r}")


def chat(*, messages, tools, meta):
    from core.services.llm_gateway import result_from_dict

    CALLS.append({"meta": dict(meta), "messages": [dict(m) for m in messages], "tools": tools})
    resp = _lookup(meta)
    if callable(resp):
        resp = resp(messages)
    if isinstance(resp, BaseException):
        raise resp
    return result_from_dict(resp)
