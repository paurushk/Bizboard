"""Q-OS backlog linter - the merge gate.

Runs checks L1-L12 (see docs/Q-OS_IMPLEMENTATION_RUNBOOK.md Appendix B) over
qos/backlog/*.yaml. Exit 1 on any failure.

    python qos/tools/lint.py             # gate the real backlog
    python qos/tools/lint.py --selftest  # prove every check can fail
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import jsonschema

from _common import (
    BACKLOG_DOC,
    enable_utf8_stdout,
    EVIDENCE_PRIORITY_CAP,
    FIXED_PLUS,
    OPEN_STATES,
    REPO_ROOT,
    SOURCE_MAP,
    TERMINAL_STATES,
    impact_band,
    load_items,
    load_schema,
    strategy_gap_ids,
)

SHA_OR_URL = re.compile(r"^[0-9a-f]{7,40}$|^https?://")


def _validator():
    return jsonschema.Draft202012Validator(load_schema())


def check_all(
    items: dict[str, dict],
    parse_errors,
    *,
    strict_gap_map: bool = True,
    backlog_doc: Path = BACKLOG_DOC,
    source_map: Path = SOURCE_MAP,
) -> list[str]:
    fails: list[str] = []
    v = _validator()

    # L1 - schema
    for path, err in parse_errors:
        fails.append(f"L1 {path.name}: {err}")
    for iid, it in items.items():
        payload = {k: val for k, val in it.items() if k != "_path"}
        for e in sorted(v.iter_errors(payload), key=str):
            loc = "/".join(str(p) for p in e.path) or "(root)"
            fails.append(f"L1 {iid}: schema: {loc}: {e.message}")

    # L2 - id unique + filename matches
    seen: dict[str, Path] = {}
    for iid, it in items.items():
        path: Path = it["_path"]
        if iid in seen and seen[iid] != path:
            fails.append(f"L2 duplicate id {iid}: {seen[iid].name} and {path.name}")
        seen.setdefault(iid, path)
        if path.stem != iid:
            fails.append(f"L2 {path.name}: filename does not match id {iid}")

    for iid, it in items.items():
        sc = it.get("scoring") or {}
        strength = (it.get("evidence") or {}).get("strength")
        prio = it.get("priority")
        cat = it.get("category")

        # L3 - evidence-strength -> priority cap (security sev-5 exempt)
        if strength in EVIDENCE_PRIORITY_CAP and prio:
            exempt = cat == "SECURITY_PRIVACY" and sc.get("severity") == 5
            if prio not in EVIDENCE_PRIORITY_CAP[strength] and not exempt:
                fails.append(
                    f"L3 {iid}: {strength} evidence cannot carry priority {prio} "
                    f"(allowed: {sorted(EVIDENCE_PRIORITY_CAP[strength])})"
                )

        # L4 - simulated needs n>=5 or a linked observation file
        if strength == "simulated":
            detail = (it.get("evidence") or {}).get("detail", "")
            m = re.search(r"n\s*=\s*(\d+)", detail)
            has_obs = any("qos/observations/" in s for s in (it.get("evidence") or {}).get("source", []))
            if not ((m and int(m.group(1)) >= 5) or has_obs):
                fails.append(f"L4 {iid}: simulated evidence needs n>=5 in detail or a qos/observations/ source")

        # L5 - impact_band recompute
        if sc:
            want = impact_band(sc)
            if sc.get("impact_band") != want:
                fails.append(f"L5 {iid}: impact_band {sc.get('impact_band')} != computed {want}")

        # L6 - ref integrity
        for field in ("depends_on", "supersedes", "duplicates"):
            for ref in it.get(field, []) or []:
                if ref == iid:
                    fails.append(f"L6 {iid}: {field} references itself")
                elif ref not in items:
                    fails.append(f"L6 {iid}: {field} -> unknown id {ref}")

        # L9 - closed date vs lifecycle
        lc = it.get("lifecycle")
        closed = it.get("closed")
        if lc in TERMINAL_STATES and not closed:
            fails.append(f"L9 {iid}: lifecycle {lc} requires a 'closed' date")
        if lc in OPEN_STATES and closed:
            fails.append(f"L9 {iid}: lifecycle {lc} must not have a 'closed' date")

        # L10 - guard_ref.test file resolves for fixed+ AND names a real test
        if lc in FIXED_PLUS:
            gr = it.get("guard_ref")
            if not gr:
                fails.append(f"L10 {iid}: lifecycle {lc} requires guard_ref")
            else:
                ref = gr["test"].strip()
                test_file, _, test_name = ref.partition("::")
                fpath = REPO_ROOT / test_file.strip()
                if not fpath.exists():
                    fails.append(f"L10 {iid}: guard_ref.test file not found: {test_file.strip()}")
                elif test_name:
                    # cheap name check - no pytest run: the name must appear as a
                    # def / it()/ test() in the file (covers pytest, vitest, playwright).
                    try:
                        body = fpath.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        body = ""
                    name = test_name.strip().split("[", 1)[0]  # drop a param id
                    if not re.search(rf"(def\s+{re.escape(name)}\b|['\"]{re.escape(name)}['\"]|\b{re.escape(name)}\s*[:(])", body):
                        fails.append(f"L10 {iid}: guard_ref names '{name}' but it is not defined in {test_file.strip()}")

        # L11 - guarded needs a red-then-green ref
        if lc == "guarded":
            failed_at = (it.get("guard_ref") or {}).get("failed_at", "")
            if not SHA_OR_URL.match(failed_at or ""):
                fails.append(f"L11 {iid}: guarded requires guard_ref.failed_at = a commit sha or run URL")

        # L12 - wontfix needs a real rationale (schema enforces length; this bars placeholders)
        if lc == "accepted_wontfix":
            wf = (it.get("wontfix_rationale") or "").strip()
            if len(wf) < 15 or re.search(r"\b(TODO|TBD|FIXME|placeholder|xxx)\b", wf, re.I):
                fails.append(f"L12 {iid}: accepted_wontfix needs a real wontfix_rationale (no placeholder text)")

    # L7 - generated doc in sync
    try:
        import build_backlog

        rendered = build_backlog.render(items)
        on_disk = backlog_doc.read_text(encoding="utf-8") if backlog_doc.exists() else ""
        if rendered != on_disk:
            fails.append("L7 docs/PRODUCT_QUALITY_BACKLOG.md is stale - run: python qos/tools/build_backlog.py")
    except Exception as exc:  # pragma: no cover - defensive
        fails.append(f"L7 could not render backlog doc: {exc}")

    # L8 - every strategy Open GAP is traced in _SOURCE_MAP.md
    gap_ids = strategy_gap_ids()
    if gap_ids:
        src_text = source_map.read_text(encoding="utf-8") if source_map.exists() else ""
        for gid in gap_ids:
            if gid not in src_text:
                msg = f"L8 strategy gap {gid} is not traced in {SOURCE_MAP.name}"
                fails.append(msg if strict_gap_map else f"[warn] {msg}")

    return fails


def _run_selftest() -> int:
    """Every fixture in _selftest/ must trip exactly the check its filename names.

    Fixture naming: ``expect_<CHECK>_<slug>.yaml`` (e.g. ``expect_L3_hypothesis_p0.yaml``).
    Each fixture is otherwise schema-valid so only its target check should fire
    for its own id (L1 schema errors, if any, are reported as a failure).
    """
    import yaml

    sd = Path(__file__).parent / "_selftest"
    fixtures = sorted(sd.glob("expect_*.yaml"))
    if not fixtures:
        print("selftest: no fixtures found in _selftest/")
        return 1
    ok = True
    for fx in fixtures:
        want = fx.stem.split("_")[1]  # expect_L3_... -> "L3"
        data = yaml.safe_load(fx.read_text(encoding="utf-8"))
        data["_path"] = fx
        items = {data["id"]: data}
        fails = check_all(items, [], strict_gap_map=False)
        own = [
            f for f in fails
            if not f.startswith("L7") and not f.startswith("L8")
            and (data["id"] in f or fx.name in f)
        ]
        tripped = [f for f in own if f.startswith(want + " ")]
        stray_schema = [f for f in own if f.startswith("L1 ") and want != "L1"]
        if tripped and not stray_schema:
            print(f"selftest OK   {fx.name}: {want} fired -> {tripped[0]}")
        elif tripped and stray_schema:
            print(f"selftest WARN {fx.name}: {want} fired but fixture also has schema errors: {stray_schema}")
        else:
            print(f"selftest FAIL {fx.name}: expected {want}; got {own or 'nothing'}")
            ok = False

    # L7 / L8 are global checks - no per-item fixture. Prove them with a temp path.
    import tempfile

    real_items, _ = load_items()
    with tempfile.TemporaryDirectory() as td:
        stale_doc = Path(td) / "stale.md"
        stale_doc.write_text("# not the real backlog\n", encoding="utf-8")
        l7 = [f for f in check_all(real_items, [], strict_gap_map=False, backlog_doc=stale_doc) if f.startswith("L7")]
        if l7:
            print(f"selftest OK   (global) L7 fired -> {l7[0]}")
        else:
            print("selftest FAIL (global): L7 did not fire against a stale backlog doc")
            ok = False

        empty_map = Path(td) / "empty_source_map.md"
        empty_map.write_text("", encoding="utf-8")
        l8 = [f for f in check_all(real_items, [], strict_gap_map=True, source_map=empty_map) if f.startswith("L8")]
        if l8:
            print(f"selftest OK   (global) L8 fired -> {l8[0]}")
        else:
            print("selftest FAIL (global): L8 did not fire against an empty source map")
            ok = False

    return 0 if ok else 1


def main() -> int:
    enable_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true", help="prove every check can fail")
    ap.add_argument("--no-gap-map", action="store_true", help="downgrade L8 to a warning")
    args = ap.parse_args()

    if args.selftest:
        return _run_selftest()

    items, parse_errors = load_items()
    fails = check_all(items, parse_errors, strict_gap_map=not args.no_gap_map)
    if fails:
        print(f"Q-OS lint: {len(fails)} problem(s)\n")
        for f in fails:
            print(f"  {f}")
        return 1
    print(f"Q-OS lint: OK ({len(items)} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
