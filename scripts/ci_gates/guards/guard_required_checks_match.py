"""Branch-protection required checks must match the CI workflow.

If a job is renamed or removed in ``.github/workflows/ci.yml`` but the
repository's required-status-checks list still names the old job, GitHub treats
the missing check as "pending" forever (or, worse, the protection is quietly
satisfied by an unrelated job). Either way a gate stops gating.

``scripts/ci_gates/REQUIRED_CHECKS.txt`` is the committed intent. This guard
asserts it equals the set of job keys actually defined in ci.yml. When you add
or rename a job, update REQUIRED_CHECKS.txt in the same commit and update the
branch-protection rule on GitHub to match.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "required_checks_match"
CONSEQUENCE = (
    "The CI workflow's jobs and the intended required-checks list have drifted; "
    "a merge gate may no longer be enforced on pull requests."
)


def _jobs_in_workflow(text: str) -> set[str]:
    jobs: set[str] = set()
    in_jobs = False
    for raw in text.splitlines():
        if re.match(r"^jobs:\s*$", raw):
            in_jobs = True
            continue
        if in_jobs:
            if raw and not raw.startswith((" ", "\t")) and not raw.startswith("#"):
                break  # left the jobs: block
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", raw)
            if m:
                jobs.add(m.group(1))
    return jobs


def _intended(text: str) -> set[str]:
    out: set[str] = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def check(root: Path) -> list[str]:
    wf = root / ".github" / "workflows" / "ci.yml"
    req = root / "scripts" / "ci_gates" / "REQUIRED_CHECKS.txt"
    if not wf.exists():
        return [f"{NAME}: {wf.relative_to(root).as_posix()} missing"]
    if not req.exists():
        return [f"{NAME}: {req.relative_to(root).as_posix()} missing"]
    jobs = _jobs_in_workflow(wf.read_text(encoding="utf-8"))
    intended = _intended(req.read_text(encoding="utf-8"))
    problems: list[str] = []
    missing = intended - jobs
    extra = jobs - intended
    if missing:
        problems.append(f"{NAME}: in REQUIRED_CHECKS.txt but not a job in ci.yml: {sorted(missing)}")
    if extra:
        problems.append(
            f"{NAME}: ci.yml jobs not listed in REQUIRED_CHECKS.txt: {sorted(extra)} "
            f"(add them, or add a '# advisory' comment line if intentionally non-blocking)"
        )
    return problems


def make_bad_tree(tmp: Path) -> None:
    (tmp / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (tmp / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  backend:\n    runs-on: x\n  frontend:\n    runs-on: x\n", encoding="utf-8"
    )
    (tmp / "scripts" / "ci_gates").mkdir(parents=True, exist_ok=True)
    (tmp / "scripts" / "ci_gates" / "REQUIRED_CHECKS.txt").write_text("backend\n", encoding="utf-8")


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print("  ", v)
        sys.exit(1)
    print(f"GUARD OK {NAME}")
