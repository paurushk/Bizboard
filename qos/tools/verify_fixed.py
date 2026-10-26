"""Run the guard test of every ``fixed`` Q-OS item and promote the passing ones to ``verified``.

The lifecycle rule (docs/Q-OS_QUALITY_PIPELINE_PLAN.md A5) says ``fixed -> verified`` needs the
guard to exist and pass in the running suite. This tool checks exactly that, with no LLM in the
loop:

* backend pytest guards run in one batched pytest call (``--junitxml``), per-item results are read
  back from the XML. An item whose tests were all skipped is NOT verified (Postgres-only tests skip
  on SQLite, so run with ``DATABASE_URL`` pointing at Postgres and ``PYTEST_KEEP_DATABASE_URL=1``
  to verify those). Backend items are only promoted from a Postgres run.
* web vitest guards run in one batched ``vitest run`` call (JSON reporter).
* anything else (Playwright e2e, CI workflow files, docs, scripts) is listed as ``manual``.

Usage (from the repo root)::

    python qos/tools/verify_fixed.py                 # report only
    python qos/tools/verify_fixed.py --apply         # also flip passing items to verified
    python qos/tools/verify_fixed.py --skip-web      # backend only

The report goes to ``qos/evidence/verify_fixed_<date>.md``. After ``--apply`` run
``python qos/tools/build_backlog.py`` and ``python qos/tools/lint.py``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from _common import BACKLOG_DIR, QOS_DIR, REPO_ROOT, enable_utf8_stdout  # type: ignore

BACKEND = REPO_ROOT / "backend"
WEB = REPO_ROOT / "web"
FILE_TIMEOUT_S = int(os.environ.get("QOS_VERIFY_FILE_TIMEOUT", "1200"))
LIFECYCLE_FIXED = re.compile(r'^lifecycle:\s*"?fixed"?\s*$', re.M)


def fixed_items() -> list[dict]:
    items = []
    for path in sorted(BACKLOG_DIR.glob("QOS-*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("lifecycle") != "fixed":
            continue
        guard = (data.get("guard_ref") or {}).get("test", "").strip()
        file_part, _, name = guard.partition("::")
        items.append({"id": data["id"], "path": path, "guard": guard, "file": file_part.strip(), "name": name.strip()})
    return items


def classify(item: dict) -> str:
    f = item["file"]
    if f.startswith("backend/tests/") and f.endswith(".py"):
        return "backend"
    if f.startswith("web/src/") and re.search(r"\.test\.tsx?$", f):
        return "web"
    return "manual"


# ---------------------------------------------------------------- backend


def run_backend(items: list[dict]) -> None:
    missing = [i for i in items if not (REPO_ROOT / i["file"]).exists()]
    for i in missing:
        i["result"], i["detail"] = "missing", "guard file does not exist"
    runnable = [i for i in items if i not in missing]
    if not runnable:
        return
    targets = sorted({i["file"].removeprefix("backend/") for i in runnable})
    # One pytest per file: a crash or hang in one guard file must not lose every other result.
    cases = []
    broken: dict[str, str] = {}
    for n, target in enumerate(targets, 1):
        xml_path = Path(tempfile.gettempdir()) / f"qos_verify_fixed_{n}.xml"
        xml_path.unlink(missing_ok=True)
        print(f"[backend {n}/{len(targets)}] {target}", flush=True)
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line",
               f"--junitxml={xml_path}", target]
        try:
            subprocess.run(cmd, cwd=BACKEND, timeout=FILE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            broken[target] = f"timed out after {FILE_TIMEOUT_S}s"
            continue
        if not xml_path.exists():
            broken[target] = "pytest exited without a report (crash?)"
            continue
        for tc in ET.parse(xml_path).getroot().iter("testcase"):
            outcome = "passed"
            for child in tc:
                if child.tag in ("failure", "error"):
                    outcome = "failed"
                elif child.tag == "skipped" and outcome == "passed":
                    outcome = "skipped"
            cases.append((tc.get("classname", ""), tc.get("name", ""), outcome))
    for i in runnable:
        if i["file"].removeprefix("backend/") in broken:
            i["result"], i["detail"] = "failed", broken[i["file"].removeprefix("backend/")]
    runnable = [i for i in runnable if i["file"].removeprefix("backend/") not in broken]
    for i in runnable:
        module = i["file"].removeprefix("backend/").removesuffix(".py").replace("/", ".")
        hits = [c for c in cases if c[0] == module or c[0].startswith(module + ".")]
        if i["name"]:
            hits = [c for c in hits if c[1] == i["name"] or c[1].startswith(i["name"] + "[")]
        i["result"], i["detail"] = judge([c[2] for c in hits])


# ---------------------------------------------------------------- web


def run_web(items: list[dict]) -> None:
    files = sorted({i["file"].removeprefix("web/") for i in items})
    out = Path(tempfile.gettempdir()) / "qos_verify_fixed_vitest.json"
    npx = "npx.cmd" if os.name == "nt" else "npx"
    print(f"[web] vitest on {len(files)} files ...", flush=True)
    subprocess.run([npx, "vitest", "run", "--reporter=json", f"--outputFile={out}", *files], cwd=WEB)
    try:
        report = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        for i in items:
            i["result"], i["detail"] = "failed", "vitest produced no JSON report"
        return
    for i in items:
        suffix = i["file"].removeprefix("web/").replace("\\", "/")
        statuses = []
        for suite in report.get("testResults", []):
            if not suite.get("name", "").replace("\\", "/").endswith(suffix):
                continue
            for a in suite.get("assertionResults", []):
                if i["name"] and i["name"] not in a.get("fullName", ""):
                    continue
                statuses.append({"passed": "passed", "skipped": "skipped", "pending": "skipped",
                                 "todo": "skipped"}.get(a.get("status"), "failed"))
        i["result"], i["detail"] = judge(statuses)


def judge(outcomes: list[str]) -> tuple[str, str]:
    if not outcomes:
        return "missing", "no matching test collected"
    if "failed" in outcomes:
        return "failed", f"{outcomes.count('failed')} of {len(outcomes)} failed"
    if all(o == "skipped" for o in outcomes):
        return "skipped", f"all {len(outcomes)} skipped (Postgres-only or env-gated?)"
    return "passed", f"{outcomes.count('passed')} passed"


# ---------------------------------------------------------------- report


def db_vendor() -> str:
    # Mirrors config/settings_test.py: outside CI the test settings drop DATABASE_URL unless
    # PYTEST_KEEP_DATABASE_URL=1, so a Postgres URL alone does not mean the run used Postgres.
    url = os.environ.get("DATABASE_URL", "")
    kept = os.environ.get("CI") or os.environ.get("PYTEST_KEEP_DATABASE_URL") == "1"
    return "postgresql" if url.startswith("postgres") and kept else "sqlite"


def main() -> int:
    enable_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="flip passing items to verified")
    ap.add_argument("--skip-web", action="store_true")
    ap.add_argument("--skip-backend", action="store_true")
    args = ap.parse_args()

    items = fixed_items()
    for i in items:
        i["kind"] = classify(i)
        i["result"], i["detail"] = ("manual", "not a backend/vitest guard") if i["kind"] == "manual" else ("not-run", "")
    if not args.skip_backend:
        run_backend([i for i in items if i["kind"] == "backend"])
    if not args.skip_web:
        web = [i for i in items if i["kind"] == "web"]
        if web:
            run_web(web)

    vendor = db_vendor()
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                         capture_output=True, text=True).stdout.strip()
    today = dt.date.today().isoformat()
    promoted = []
    if args.apply:
        for i in items:
            # A backend guard only counts when it ran on Postgres, the production database.
            ok = i["result"] == "passed" and (i["kind"] == "web" or vendor == "postgresql")
            if not ok:
                continue
            text = i["path"].read_text(encoding="utf-8")
            quoted = '"' if re.search(r'^lifecycle:\s*"', text, re.M) else ""
            i["path"].write_text(LIFECYCLE_FIXED.sub(f"lifecycle: {quoted}verified{quoted}", text, count=1),
                                 encoding="utf-8")
            promoted.append(i["id"])

    counts: dict[str, int] = {}
    for i in items:
        counts[i["result"]] = counts.get(i["result"], 0) + 1
    lines = [f"# verify_fixed — {today}", "",
             f"Commit `{sha}` (plus working tree) · backend DB: **{vendor}** · apply: {args.apply}", "",
             "Summary: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
             f"Promoted to verified: {len(promoted)}" + (f" ({', '.join(promoted)})" if promoted else ""), "",
             "| Item | Kind | Result | Detail | Guard |", "|---|---|---|---|---|"]
    order = {"failed": 0, "missing": 1, "skipped": 2, "manual": 3, "not-run": 4, "passed": 5}
    for i in sorted(items, key=lambda x: (order.get(x["result"], 9), x["id"])):
        lines.append(f"| {i['id']} | {i['kind']} | {i['result']} | {i['detail']} | `{i['guard']}` |")
    out = QOS_DIR / "evidence" / f"verify_fixed_{today}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:6]))
    print(f"Report: {out.relative_to(REPO_ROOT)}")
    return 1 if counts.get("failed") or counts.get("missing") else 0


if __name__ == "__main__":
    raise SystemExit(main())
