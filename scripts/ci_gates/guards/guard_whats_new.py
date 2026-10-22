"""WP-CM3 — every "What's new" entry has Hindi text, and the doc lists the same entries.

``web/src/help/whatsNew.ts`` is the source for the in-app panel; ``docs/help/WHATS_NEW.md`` lists
the same ids as ``## <id> — <title>`` headings. An entry with empty or untranslated Hindi text
shows English to a Hindi user; a doc that drifts tells support about features that are not there.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "whats_new"
CONSEQUENCE = "Hindi users see untranslated release notes, or the docs describe a different release."

_SRC = "web/src/help/whatsNew.ts"
_DOC = "docs/help/WHATS_NEW.md"
_STR = r"'((?:[^'\\]|\\.)*)'"
_ENTRY = re.compile(
    r"id:\s*'([^']+)'.*?en:\s*\{\s*title:\s*" + _STR + r".*?body:\s*" + _STR + r".*?"
    r"hi:\s*\{\s*title:\s*" + _STR + r".*?body:\s*" + _STR,
    re.S,
)
_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")


def check(root: Path) -> list[str]:
    src, doc = root / _SRC, root / _DOC
    if not src.exists() or not doc.exists():
        return [f"{_SRC} and {_DOC} must both exist"]
    out: list[str] = []
    entries = _ENTRY.findall(src.read_text(encoding="utf-8"))
    if not entries:
        out.append(f"{_SRC}: no entries found")
    ids = set()
    for eid, en_t, en_b, hi_t, hi_b in entries:
        ids.add(eid)
        if not _ID.match(eid):
            out.append(f"{_SRC}: id '{eid}' must look like 2026-10-22-short-name")
        if not hi_t.strip() or not hi_b.strip():
            out.append(f"{_SRC}: '{eid}' has no Hindi text")
        elif hi_t.strip() == en_t.strip() or hi_b.strip() == en_b.strip():
            out.append(f"{_SRC}: '{eid}' Hindi text is the English text")
    doc_ids = set(re.findall(r"^##\s+(\S+)\s+—", doc.read_text(encoding="utf-8"), re.M))
    for eid in sorted(ids - doc_ids):
        out.append(f"{_DOC}: entry '{eid}' is in the app but not in the doc")
    for eid in sorted(doc_ids - ids):
        out.append(f"{_SRC}: entry '{eid}' is in the doc but not in the app")
    return out


def make_bad_tree(tmp: Path) -> None:
    (tmp / "web" / "src" / "help").mkdir(parents=True)
    (tmp / _SRC).write_text(
        "export const WHATS_NEW = [{ id: '2026-10-22-x', en: { title: 'A', body: 'B' }, "
        "hi: { title: 'A', body: '' } }];\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "help").mkdir(parents=True)
    (tmp / _DOC).write_text("## 2026-10-21-y — Other\n", encoding="utf-8")


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
