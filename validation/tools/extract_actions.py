"""Validate the hand-seeded in-page action registry.

    python validation/tools/extract_actions.py
    python validation/tools/extract_actions.py --selftest
"""

from __future__ import annotations

import argparse
import sys

import jsonschema

from _common import ACTION_SCHEMA, ACTIONS_YAML, load_json, load_yaml

MIN_ACTIONS = 14


def load_actions(path=ACTIONS_YAML) -> list[dict]:
    data = load_yaml(path) or {}
    return list(data.get("actions") or [])


def validate_actions(actions: list[dict], schema_path=ACTION_SCHEMA) -> list[str]:
    schema = load_json(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    if len(actions) < MIN_ACTIONS:
        errors.append(f"actions.yaml has {len(actions)} entries; need >= {MIN_ACTIONS} (§2.13)")
    seen: set[str] = set()
    for i, item in enumerate(actions):
        iid = item.get("id", f"#{i}")
        if iid in seen:
            errors.append(f"duplicate action id {iid}")
        seen.add(iid)
        for err in sorted(validator.iter_errors(item), key=str):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            errors.append(f"{iid}: {loc}: {err.message}")
    return errors


def _selftest() -> int:
    actions = load_actions()
    errs = validate_actions(actions)
    if errs:
        print("FAIL real actions.yaml is invalid:")
        for e in errs:
            print(f"  {e}")
        return 1
    print(f"ok    actions.yaml ({len(actions)} entries, schema-valid)")
    bad = [{"id": "x", "title": "short"}]
    if not validate_actions(bad):
        print("FAIL schema did not reject a truncated action")
        return 1
    print("ok    schema rejects truncated action")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    errs = validate_actions(load_actions())
    if errs:
        print("actions.yaml:")
        for e in errs:
            print(f"  {e}")
        return 1
    print(f"actions.yaml OK ({len(load_actions())} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
