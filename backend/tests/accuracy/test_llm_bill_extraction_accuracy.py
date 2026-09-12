"""QOS-0015 — LLM purchase-bill extraction accuracy benchmark.

This is the harness shell only: the failure paths (timeout, malformed JSON,
etc.) are already covered by tests/errors/test_llm_extraction_failures.py
with a mocked provider. What's been missing is a floor on *accuracy* — "did
the extraction actually get the fields right" — which needs a corpus of
real bill photos with known-correct field values. This session has none (a
synthetic/rendered "bill" would be trivially easy for a vision model and
would measure nothing about real-world accuracy), so the corpus directory
(tests/fixtures/bill_accuracy_corpus/) ships empty with instructions — this
test SKIPS cleanly until real cases are added, it does not fail the suite.

Calls the real configured LLM provider — real API cost, not mocked. Marked
`llm_accuracy` (see pytest.ini) so it never runs as part of the default
`pytest` invocation; opt in explicitly with `-m llm_accuracy`.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

from core.services.llm import extract_purchase_bill

pytestmark = [pytest.mark.llm_accuracy, pytest.mark.django_db]

CORPUS_DIR = Path(__file__).parent.parent / "fixtures" / "bill_accuracy_corpus"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")

# Conservative until the corpus has enough cases to trust the number — raise
# this deliberately as real cases accumulate, never lower it without a note
# on why the floor moved.
ACCURACY_FLOOR = 0.7


def _discover_cases() -> list[tuple[Path, Path]]:
    if not CORPUS_DIR.exists():
        return []
    cases = []
    for json_path in sorted(CORPUS_DIR.glob("*.json")):
        image_path = next(
            (json_path.with_suffix(ext) for ext in IMAGE_SUFFIXES if json_path.with_suffix(ext).exists()),
            None,
        )
        if image_path:
            cases.append((image_path, json_path))
    return cases


def _norm_str(value) -> str:
    return str(value or "").strip().upper()


def _norm_amount(value) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _field_match(expected, actual) -> bool:
    if expected is None:
        return True  # not scored — the case didn't specify this field
    exp_amount, act_amount = _norm_amount(expected), _norm_amount(actual)
    if exp_amount is not None and act_amount is not None:
        return abs(exp_amount - act_amount) < Decimal("0.01")
    return _norm_str(expected) == _norm_str(actual)


def _score_case(expected: dict, actual: dict) -> tuple[int, int]:
    """(fields matched, fields scored) across header + best-effort line matching."""
    matched = 0
    scored = 0
    for key in ("supplier_name", "supplier_gstin", "bill_number", "bill_date"):
        if key not in expected:
            continue
        scored += 1
        if _field_match(expected[key], actual.get(key)):
            matched += 1

    expected_lines = expected.get("lines") or []
    actual_lines = list(actual.get("lines") or [])
    for exp_line in expected_lines:
        # Best-effort pairing: the closest actual line by name, consumed once
        # matched so a corpus with repeated line names doesn't double-count.
        best_idx, best_hits = None, -1
        for idx, act_line in enumerate(actual_lines):
            hits = sum(
                1 for k in ("name", "quantity", "unit_price", "gst_rate")
                if k in exp_line and _field_match(exp_line[k], act_line.get(k))
            )
            if hits > best_hits:
                best_idx, best_hits = idx, hits
        line_scored = sum(1 for k in ("name", "quantity", "unit_price", "gst_rate") if k in exp_line)
        scored += line_scored
        if best_idx is not None:
            matched += best_hits
            actual_lines.pop(best_idx)
    return matched, scored


@pytest.mark.parametrize("image_path,json_path", _discover_cases() or [pytest.param(None, None, id="no-corpus")])
def test_extraction_matches_expected_fields(image_path, json_path):
    if image_path is None:
        pytest.skip(
            "No bill corpus present — add real bill images + expected JSON to "
            "tests/fixtures/bill_accuracy_corpus/ to activate this lane (see its README)."
        )
    expected = json.loads(json_path.read_text(encoding="utf-8"))
    actual = extract_purchase_bill([image_path.read_bytes()])

    matched, scored = _score_case(expected, actual)
    accuracy = (matched / scored) if scored else 1.0
    assert accuracy >= ACCURACY_FLOOR, (
        f"{json_path.name}: {matched}/{scored} fields matched ({accuracy:.0%}), "
        f"below the {ACCURACY_FLOOR:.0%} floor. actual={actual!r}"
    )
