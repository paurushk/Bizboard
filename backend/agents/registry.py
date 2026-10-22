"""Tool registry. Tools are company-scoped functions an agent may call; arguments are DRF serializers.

A tool never accepts company_id from the model: the registry strips it and ToolContext carries the
company. Registering a tool with ``money=True`` is refused outright: agents never move money.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from rest_framework import serializers

from core.exceptions import BusinessRuleError

from .enums import Autonomy
from .error_codes import AGT_E_ROLE, AGT_E_UNKNOWN_TOOL, AGT_E_VALIDATION

_STRIPPED_ARGS = ("company_id", "company")


@dataclass
class ToolContext:
    company: Any
    company_user: Any = None
    run: Any = None
    as_of: date | None = None
    extras: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., dict]
    args: type[serializers.Serializer] | None
    access: Callable[[Any], bool] | None      # callable(company_user) -> bool; None = any
    autonomy: int
    money: bool
    max_result_rows: int


REGISTRY: dict[str, ToolSpec] = {}


def tool(
    *,
    name: str,
    description: str = "",
    args: type[serializers.Serializer] | None = None,
    access: Callable[[Any], bool] | None = None,
    autonomy: int = Autonomy.L1,
    money: bool = False,
    max_result_rows: int = 50,
):
    if money:
        raise RuntimeError(f"Tool {name}: agents may not register money-moving tools.")

    def deco(fn):
        if name in REGISTRY:
            raise RuntimeError(f"Duplicate tool {name}")
        REGISTRY[name] = ToolSpec(
            name=name,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
            fn=fn,
            args=args,
            access=access,
            autonomy=int(autonomy),
            money=False,
            max_result_rows=max_result_rows,
        )
        return fn

    return deco


def _serializer_json_schema(serializer_cls) -> dict:
    """Small JSON-schema export for the provider tool definition, derived from the serializer."""
    if serializer_cls is None:
        return {"type": "object", "properties": {}}
    props: dict[str, dict] = {}
    required: list[str] = []
    for fname, field_ in serializer_cls().fields.items():
        if field_.read_only:
            continue
        if isinstance(field_, serializers.BooleanField):
            typ = {"type": "boolean"}
        elif isinstance(field_, serializers.IntegerField):
            typ = {"type": "integer"}
        elif isinstance(field_, (serializers.FloatField, serializers.DecimalField)):
            typ = {"type": "number"}
        elif isinstance(field_, serializers.ListField):
            typ = {"type": "array", "items": {"type": "string"}}
        elif isinstance(field_, serializers.ChoiceField):
            typ = {"type": "string", "enum": [str(c) for c in field_.choices]}
        else:
            typ = {"type": "string"}
        if field_.help_text:
            typ["description"] = str(field_.help_text)
        props[fname] = typ
        if field_.required:
            required.append(fname)
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def export_json_schema(name: str) -> dict:
    spec = REGISTRY[name]
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": _serializer_json_schema(spec.args),
        },
    }


def specs_for(tool_names: list[str]) -> list[dict]:
    return [export_json_schema(n) for n in tool_names if n in REGISTRY]


def invoke(name: str, raw_args: dict | None, ctx: ToolContext, *, allowlist: list[str]) -> dict:
    """Validate and run one tool call. Raises BusinessRuleError on any policy or validation problem."""
    spec = REGISTRY.get(name)
    if spec is None or name not in allowlist:
        raise BusinessRuleError(f"Unknown tool: {name}", code=AGT_E_UNKNOWN_TOOL)
    if spec.access is not None and ctx.company_user is not None and not spec.access(ctx.company_user):
        raise BusinessRuleError("Your role does not have access to this data.", code=AGT_E_ROLE)
    args = dict(raw_args) if isinstance(raw_args, dict) else {}
    for key in _STRIPPED_ARGS:
        args.pop(key, None)
    if spec.args is not None:
        ser = spec.args(data=args)
        if not ser.is_valid():
            raise BusinessRuleError(f"Bad arguments for {name}: {ser.errors}", code=AGT_E_VALIDATION)
        args = dict(ser.validated_data)
    result = spec.fn(ctx, **args)
    return _cap_rows(result, spec.max_result_rows)


def _cap_rows(result: Any, limit: int) -> Any:
    if isinstance(result, dict):
        out = {}
        for k, v in result.items():
            if isinstance(v, list) and len(v) > limit:
                out[k] = v[:limit]
                out[f"{k}_truncated"] = True
            else:
                out[k] = v
        return out
    return result
