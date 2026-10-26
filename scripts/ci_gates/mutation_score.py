"""Per-module mutation score gate (stabilization WP-5).

Reads ``python -m mutmut results --all true`` (run from backend/ after ``mutmut run``), computes
a score per mutated module, and fails when a module drops below its recorded baseline, so the
test suite can only get stronger. Score = killed (incl. timeout) / every mutant that ran or
had no test; a mutant no test covers counts against the score, it is a coverage hole.

Usage (from the repo root)::

    python scripts/ci_gates/mutation_score.py results.txt            # gate
    python scripts/ci_gates/mutation_score.py results.txt --update   # record a new baseline

``results.txt`` is the saved output of ``mutmut results --all true``; ``-`` reads stdin.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASELINE = Path(__file__).with_name("mutation_baseline.json")
LINE = re.compile(r"^\s*(?P<name>[\w.]+?)\.x[_ǁ]\S*__mutmut_\d+:\s*(?P<status>[\w ]+?)\s*$")
KILLED = {"killed", "timeout"}
COUNTED = KILLED | {"survived", "no tests", "suspicious"}
TOLERANCE = 0.01  # a different random-free run can move one or two mutants


def scores(text: str) -> dict[str, dict]:
    per: dict[str, dict] = {}
    for line in text.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        status = m["status"].strip().lower()
        if status not in COUNTED:
            continue
        row = per.setdefault(m["name"], {"killed": 0, "total": 0})
        row["total"] += 1
        row["killed"] += status in KILLED
    for row in per.values():
        row["score"] = round(row["killed"] / row["total"], 4) if row["total"] else 0.0
    return per


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results")
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    text = sys.stdin.read() if args.results == "-" else Path(args.results).read_text(encoding="utf-8")
    current = scores(text)
    if not current:
        print("mutation_score: no mutant results found; did `mutmut run` actually run?")
        return 1
    for mod, row in sorted(current.items()):
        print(f"{mod:45} {row['score']:.1%}  ({row['killed']}/{row['total']} killed)")
    if args.update:
        # Merge: a run over some modules (mutmut source_paths narrowed) keeps the others' baselines.
        merged = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
        merged.update({m: r["score"] for m, r in current.items()})
        BASELINE.write_text(json.dumps(dict(sorted(merged.items())), indent=2) + "\n")
        print(f"baseline written: {BASELINE}")
        return 0
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    drops = [f"{m}: {current[m]['score']:.1%} < baseline {b:.1%}"
             for m, b in baseline.items() if m in current and current[m]["score"] < b - TOLERANCE]
    for d in drops:
        print(f"REGRESSION {d}")
    return 1 if drops else 0


if __name__ == "__main__":
    raise SystemExit(main())
