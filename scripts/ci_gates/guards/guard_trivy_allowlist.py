"""WP-SC3 — every image-scan exception is justified and has an expiry that has not passed.

``security/trivy-allowlist.yaml`` lets a reviewed CVE through the CI image scan. An entry with no
reason, or no expiry, or an expiry in the past, means a known-vulnerable image ships with nobody
looking at it again.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

NAME = "trivy_allowlist"
CONSEQUENCE = "A known CVE is waved through the image scan with no reason or review date."

_FILE = "security/trivy-allowlist.yaml"


def check(root: Path) -> list[str]:
    import yaml

    path = root / _FILE
    if not path.exists():
        return [f"{_FILE} is missing (an empty 'vulnerabilities: []' is fine)"]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [f"{_FILE}: not valid YAML ({exc})"]
    out: list[str] = []
    today = dt.date.today()
    for i, entry in enumerate(data.get("vulnerabilities") or [], start=1):
        if not isinstance(entry, dict):
            out.append(f"{_FILE}: entry {i} is not a mapping")
            continue
        vid = entry.get("id") or f"entry {i}"
        if not str(entry.get("statement") or "").strip():
            out.append(f"{_FILE}: {vid} has no 'statement' saying why it is accepted")
        raw = entry.get("expired_at")
        if not raw:
            out.append(f"{_FILE}: {vid} has no 'expired_at' review date")
            continue
        try:
            when = raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
        except ValueError:
            out.append(f"{_FILE}: {vid} 'expired_at' must be YYYY-MM-DD")
            continue
        if when < today:
            out.append(f"{_FILE}: {vid} expired on {when}; review it again or remove it")
    return out


def make_bad_tree(tmp: Path) -> None:
    (tmp / "security").mkdir(parents=True)
    (tmp / _FILE).write_text(
        "vulnerabilities:\n  - id: CVE-2020-1\n  - id: CVE-2020-2\n    statement: old\n    expired_at: 2020-01-01\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print(f"  - {v}")
        sys.exit(1)
    print(f"GUARD OK {NAME}")
