"""Backup, wipe and restore for the agents tables (AGT-108).

Order matters: proposals point at runs with PROTECT, so wipe walks the list backward (steps, aliases,
proposals, runs) and restore walks it forward. Step records are an operational log with their own
180-day retention, so they are wiped with the tenant but not exported.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps

# (payload key, "app.Model", {field: map name}, fields to require, fields to leave out, map name this table fills)
SPECS: list[tuple[str, str, dict[str, str], tuple[str, ...], set[str], str | None]] = [
    ("agent_runs", "agents.AgentRun", {}, (), {"requested_by_id"}, "agent_run"),
    (
        "agent_proposals", "agents.AgentProposal", {"run_id": "agent_run"}, ("run_id",),
        {"assignee_id", "decided_by_id"}, None,
    ),
    (
        "agent_aliases", "agents.AgentAlias", {"customer_id": "customer", "product_id": "product"}, (), set(), None,
    ),
]


def _model(label: str):
    app, name = label.split(".")
    return apps.get_model(app, name)


def export_rows(company, extra: dict, optional_rows) -> None:
    for key, label, *_ in SPECS:
        try:
            extra[key] = optional_rows(_model(label), company)
        except Exception:
            extra[key] = []


def wipe(company) -> None:
    """Steps, aliases, proposals, then runs."""
    try:
        _model("agents.AgentStep").objects.filter(company=company).delete()
    except Exception:
        pass
    for _key, label, *_ in reversed(SPECS):
        try:
            _model(label).objects.filter(company=company).delete()
        except Exception:
            continue


def restore(*, payload: dict, target_company, owner, maps: dict[str, dict[Any, int]], create_mapped) -> None:
    own: dict[str, dict[Any, int]] = {}
    lookup = {**maps}
    for key, label, remap, require, skip, fills in SPECS:
        model = _model(label)
        resolved = {fld: lookup.setdefault(name, {}) for fld, name in remap.items()}
        table = own.setdefault(fills, {}) if fills else None
        for row in payload.get(key) or []:
            try:
                obj = create_mapped(model, row, company=target_company, owner=owner, skip=set(skip), remap=resolved, require=require)
            except Exception:
                continue
            if obj is not None and table is not None:
                table[row.get("id")] = obj.pk
        if fills:
            lookup[fills] = own[fills]
