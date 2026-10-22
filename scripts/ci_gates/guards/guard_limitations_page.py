"""WP-PO1 — the customer-facing limitations page matches its source doc in both languages.

``docs/help/LIMITATIONS.md`` lists each limitation as ``key: <name>``. The page
(``web/src/pages/help/PilotLimitsPage.tsx`` ``KEYS``) must show exactly those keys, and
``pilotLimits.<key>`` must exist in ``en.ts`` and ``hi.ts``. A limitation dropped from the page
but still true gets the product sold for something it doesn't do.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "limitations_page"
CONSEQUENCE = "The limitations customers read drift from what the product actually doesn't do."

_DOC = "docs/help/LIMITATIONS.md"
_PAGE = "web/src/pages/help/PilotLimitsPage.tsx"
_LOCALES = ("web/src/i18n/en.ts", "web/src/i18n/hi.ts")


def _block(text: str) -> str:
    m = re.search(r"pilotLimits:\s*\{(.*?)\n\s*\},", text, re.S)
    return m.group(1) if m else ""


def check(root: Path) -> list[str]:
    doc_path, page_path = root / _DOC, root / _PAGE
    if not doc_path.exists() or not page_path.exists():
        return [f"{_DOC} and {_PAGE} must both exist"]
    doc_keys = set(re.findall(r"key:\s*([A-Za-z0-9_]+)", doc_path.read_text(encoding="utf-8")))
    page = page_path.read_text(encoding="utf-8")
    m = re.search(r"const KEYS = \[(.*?)\]", page, re.S)
    page_keys = set(re.findall(r"'([A-Za-z0-9_]+)'", m.group(1))) if m else set()
    out: list[str] = []
    for k in sorted(doc_keys - page_keys):
        out.append(f"{_PAGE}: '{k}' is in {_DOC} but not shown on the page")
    for k in sorted(page_keys - doc_keys):
        out.append(f"{_DOC}: page shows '{k}' but the doc does not list it")
    for loc in _LOCALES:
        path = root / loc
        block = _block(path.read_text(encoding="utf-8")) if path.exists() else ""
        have = set(re.findall(r"^\s*([A-Za-z0-9_]+):", block, re.M))
        for k in sorted(page_keys - have):
            out.append(f"{loc}: pilotLimits.{k} is missing")
    return out


def make_bad_tree(tmp: Path) -> None:
    (tmp / "docs" / "help").mkdir(parents=True)
    (tmp / _DOC).write_text("| key: filing | x |\n| key: tally | y |\n", encoding="utf-8")
    (tmp / "web" / "src" / "pages" / "help").mkdir(parents=True)
    (tmp / _PAGE).write_text("const KEYS = ['filing'] as const;\n", encoding="utf-8")
    (tmp / "web" / "src" / "i18n").mkdir(parents=True)
    for loc in _LOCALES:
        (tmp / loc).write_text("  pilotLimits: {\n    filing: 'x',\n  },\n", encoding="utf-8")


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
