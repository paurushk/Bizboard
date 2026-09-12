"""The CA-signed GST scenarios stay covered by the automated parity fixture.

`docs/ca/CA_SIGN_OFF_CHECKLIST.md` lists tax scenarios **F1–F8** that a
practising CA signed off against the frozen Tax Invoice template. The checklist
says: "Automated parity fixture must cover the same set
(`tax_parity_cases.json` + FE/BE tests)."

This guard fails if a CA scenario silently loses its automated case — i.e. one
of the `f1_`…`f8_` prefixes disappears from
`backend/tests/fixtures/tax_parity_cases.json`, or the checklist stops pointing
at that fixture. Either means the CA sign-off no longer maps to what the code
actually computes, and the presentation change needs re-CA.
"""

from __future__ import annotations

import json
from pathlib import Path

NAME = "ca_tax_parity"
CONSEQUENCE = (
    "A CA-signed GST scenario (F1-F8) lost its automated parity case, or the CA "
    "checklist no longer references the fixture — the sign-off no longer "
    "corresponds to the computed tax, and a presentation change could ship "
    "un-reviewed."
)

_REQUIRED_PREFIXES = tuple(f"f{n}_" for n in range(1, 9))
_FIXTURE_REL = "backend/tests/fixtures/tax_parity_cases.json"
_CHECKLIST_REL = "docs/ca/CA_SIGN_OFF_CHECKLIST.md"


def check(root: Path) -> list[str]:
    out: list[str] = []
    fixture = root / _FIXTURE_REL
    checklist = root / _CHECKLIST_REL

    if not fixture.exists():
        return [f"{NAME}: {_FIXTURE_REL} is missing"]
    try:
        cases = json.loads(fixture.read_text(encoding="utf-8"))
        ids = {str(c.get("id", "")) for c in cases}
    except (ValueError, TypeError, AttributeError) as exc:
        return [f"{NAME}: {_FIXTURE_REL} is not a readable list of cases ({exc})"]

    for prefix in _REQUIRED_PREFIXES:
        if not any(i.startswith(prefix) for i in ids):
            out.append(
                f"{NAME}: no parity case '{prefix}*' in {_FIXTURE_REL} — CA "
                f"scenario F{prefix[1]} is uncovered"
            )

    if not checklist.exists():
        out.append(f"{NAME}: {_CHECKLIST_REL} is missing")
    elif "tax_parity_cases.json" not in checklist.read_text(encoding="utf-8"):
        out.append(
            f"{NAME}: {_CHECKLIST_REL} no longer points at tax_parity_cases.json"
        )
    return out


def make_bad_tree(tmp: Path) -> None:
    fx = tmp / _FIXTURE_REL
    fx.parent.mkdir(parents=True, exist_ok=True)
    # only f1 + f2 present -> F3-F8 uncovered
    fx.write_text(
        json.dumps([{"id": "f1_even_200_18"}, {"id": "f2_inter_100_12"}]),
        encoding="utf-8",
    )
    cl = tmp / _CHECKLIST_REL
    cl.parent.mkdir(parents=True, exist_ok=True)
    cl.write_text("# checklist without the fixture reference\n", encoding="utf-8")


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
