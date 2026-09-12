"""Merge a freshly-mined item over an on-disk one, preserving human-owned fields.

The re-mine (``_backfill_phase1.py`` today, any future miner) regenerates the
*content* fields from source docs. The *workflow* fields belong to whoever has
been triaging the backlog and must survive a re-mine untouched.

    merged = merge.apply(generated_dict, existing_dict)

If ``existing`` is None (new item) ``generated`` is returned unchanged.
"""

from __future__ import annotations

# Fields the miner owns — always taken from the freshly-generated item.
GENERATED_FIELDS = {
    "id", "category", "title", "persona", "archetype", "journey", "problem",
    "evidence", "scoring", "business_metric", "supersedes", "duplicates",
}

# Fields a human owns once triage starts — preserved from the on-disk item.
HUMAN_FIELDS = {
    "priority", "priority_rationale", "effort", "recommendation", "test_required",
    "guard_ref", "lifecycle", "wontfix_rationale", "depends_on", "owner",
    "opened", "closed",
}


def apply(generated: dict, existing: dict | None) -> dict:
    if not existing:
        return dict(generated)
    out = dict(generated)
    for key in HUMAN_FIELDS:
        if key in existing:
            out[key] = existing[key]
        elif key in out:
            # human dropped an optional field (e.g. depends_on) — respect that
            if key not in ("priority", "priority_rationale", "effort",
                           "recommendation", "test_required", "lifecycle",
                           "owner", "opened"):
                del out[key]
    return out


def describe_overrides(generated: dict, existing: dict | None) -> list[str]:
    """Human-readable list of fields that the on-disk item overrides — for logging."""
    if not existing:
        return []
    diffs = []
    for key in HUMAN_FIELDS:
        if key in existing and existing.get(key) != generated.get(key):
            diffs.append(key)
    return diffs
