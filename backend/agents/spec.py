"""Agent plug-in contract (plan 3.10).

An agent is a package under agents/catalog/<name>/ whose __init__ exposes ``AGENT = AgentSpec(...)``.
``autodiscover()`` imports those packages at start-up and fills ``AGENTS`` and ``PROPOSAL_KINDS``.
The platform (runner, policy, services, API, scheduler, UI shell) only ever reads these registries.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

FLAG_PREFIX = "AGENT_"
RENDERERS = ("message", "lines", "comparison", "order")


class SpecError(Exception):
    """Raised at start-up for an invalid or duplicate spec."""


@dataclass(frozen=True)
class ProposalKindSpec:
    kind: str
    payload_serializers: dict[int, Any]            # schema_version -> DRF serializer class
    executor: Callable[..., dict] | None           # (proposal, ctx) -> result_ref; None = copy-only
    renderer: str = "message"
    default_ttl_hours: int = 72
    bulk_approvable: bool = False
    approve_permission: Any = None                 # callable(company_user) -> bool
    title_key: str = ""
    autonomy: int = 2

    @property
    def current_version(self) -> int:
        return max(self.payload_serializers)


@dataclass(frozen=True)
class AgentSpec:
    kind: str
    flag: str
    title_key: str
    proposal_kinds: list[ProposalKindSpec]
    tools: list[str]
    # context_builder(tctx) -> {"facts": {...}, "untrusted": {name: text}?, "rules_only": bool?}
    context_builder: Callable[..., dict]
    parse_final: Callable[..., list[dict]]         # (tctx, context, model_text) -> drafts; raise ValueError if malformed
    validate: Callable[..., None]                  # (tctx, context, drafts); raise BusinessRuleError to reject
    rules_only: Callable[..., list[dict]]          # (tctx, context) -> drafts, no model
    prepare_permission: Any = None                 # callable(company_user) -> bool
    trigger_codes: list[str] = field(default_factory=list)
    attention_codes: list[str] = field(default_factory=list)
    schedule: dict | None = None                   # {"hour": 8, "minute": 30} IST, None = on demand only
    usage_feature_kind: str = ""
    limits: dict = field(default_factory=dict)
    requires_flags: list[str] = field(default_factory=list)
    prompt_names: list[str] = field(default_factory=lambda: ["system"])
    package: str = ""                              # catalog dirname; set by autodiscover()
    # still_open(company, dedupe_keys) -> iterable of keys whose condition still holds; None = never auto-cancel
    still_open: Callable[..., Any] | None = None
    # True for agents that start from pasted text (Order Intake). The run is then synchronous: the person
    # waits for the draft, and the text is handed to the hooks via tctx.extras["text"], never stored on the run.
    accepts_text: bool = False
    text_max_chars: int = 6000

    def limit(self, name: str, default):
        return self.limits.get(name, default)

    def matches_code(self, code: str) -> bool:
        for pattern in self.trigger_codes:
            if pattern.endswith("*"):
                if code.startswith(pattern[:-1]):
                    return True
            elif pattern == code:
                return True
        return False


AGENTS: dict[str, AgentSpec] = {}
PROPOSAL_KINDS: dict[str, ProposalKindSpec] = {}
_AGENT_OF_KIND: dict[str, str] = {}


def _package_of(spec: AgentSpec) -> str:
    """The catalog dirname, from the module that defines the spec's hooks (agents.catalog.<pkg>.*)."""
    parts = getattr(spec.context_builder, "__module__", "").split(".")
    return parts[2] if len(parts) >= 3 and parts[:2] == ["agents", "catalog"] else ""


def register(spec: AgentSpec) -> None:
    if not spec.package:
        object.__setattr__(spec, "package", _package_of(spec))
    if spec.kind in AGENTS:
        raise SpecError(f"Duplicate agent kind {spec.kind}")
    if not spec.flag.startswith(FLAG_PREFIX):
        raise SpecError(f"Agent {spec.kind}: flag must start with {FLAG_PREFIX}")
    if spec.accepts_text and spec.schedule:
        raise SpecError(f"Agent {spec.kind}: an agent that starts from pasted text cannot run on a schedule")
    for pk in spec.proposal_kinds:
        if pk.kind in PROPOSAL_KINDS:
            raise SpecError(f"Duplicate proposal kind {pk.kind}")
        if pk.renderer not in RENDERERS:
            raise SpecError(f"Proposal kind {pk.kind}: unknown renderer {pk.renderer}")
        if not pk.payload_serializers:
            raise SpecError(f"Proposal kind {pk.kind}: needs a payload serializer")
    from agents import registry
    from agents.prompts import prompt_exists

    for name in spec.prompt_names:
        if not prompt_exists(spec.package, name):
            raise SpecError(f"Agent {spec.kind}: missing prompt {name!r} in catalog/{spec.package or '?'}/prompts")
    for name in spec.tools:
        if name not in registry.REGISTRY:
            raise SpecError(f"Agent {spec.kind}: unknown tool {name}")
    AGENTS[spec.kind] = spec
    for pk in spec.proposal_kinds:
        PROPOSAL_KINDS[pk.kind] = pk
        _AGENT_OF_KIND[pk.kind] = spec.kind


def unregister(kind: str) -> None:
    """Test helper."""
    spec = AGENTS.pop(kind, None)
    if spec:
        for pk in spec.proposal_kinds:
            PROPOSAL_KINDS.pop(pk.kind, None)
            _AGENT_OF_KIND.pop(pk.kind, None)


def get_agent(kind: str) -> AgentSpec:
    from agents.error_codes import AGT_E_UNKNOWN_AGENT
    from core.exceptions import BusinessRuleError

    spec = AGENTS.get(kind)
    if spec is None:
        raise BusinessRuleError(f"Unknown agent {kind}", code=AGT_E_UNKNOWN_AGENT)
    return spec


def get_kind(kind: str) -> ProposalKindSpec:
    from agents.error_codes import AGT_E_UNKNOWN_KIND
    from core.exceptions import BusinessRuleError

    spec = PROPOSAL_KINDS.get(kind)
    if spec is None:
        raise BusinessRuleError(f"Unknown proposal kind {kind}", code=AGT_E_UNKNOWN_KIND)
    return spec


def agent_for_kind(kind: str) -> str | None:
    return _AGENT_OF_KIND.get(kind)


def autodiscover() -> None:
    """Import agents.catalog.* and register each package's AGENT. Idempotent."""
    from agents import catalog

    for mod in pkgutil.iter_modules(catalog.__path__):
        if mod.name.startswith("_") or not mod.ispkg:
            continue
        module = importlib.import_module(f"agents.catalog.{mod.name}")
        agent = getattr(module, "AGENT", None)
        if agent is not None and agent.kind not in AGENTS:
            if not agent.package:
                object.__setattr__(agent, "package", mod.name)
            register(agent)
