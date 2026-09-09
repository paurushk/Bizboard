"""The regression corpus only grows.

Every bug fixed from freeze onward lands one permanent test under
``backend/tests/regression/`` (see that folder's README). This guard counts the
``def test_*`` functions there and fails if the live count drops below the
committed baseline in ``backend/tests/regression/.corpus_count``. An LLM (or a
human) cannot quietly delete a regression test without the diff to that file
making it obvious.

To legitimately remove a regression test: delete it, lower ``.corpus_count`` in
the same commit, and say why in the commit message.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "regression_corpus_grows"
CONSEQUENCE = (
    "A regression test was deleted without lowering the recorded baseline; a "
    "previously-fixed bug is no longer protected and can silently return."
)

_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+test_\w+", re.MULTILINE)


def _count(corpus: Path) -> int:
    n = 0
    for py in corpus.rglob("test_*.py"):
        try:
            n += len(_TEST_DEF.findall(py.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return n


def check(root: Path) -> list[str]:
    corpus = root / "backend" / "tests" / "regression"
    baseline_file = corpus / ".corpus_count"
    if not corpus.exists():
        return [f"{NAME}: {corpus.relative_to(root).as_posix()} is missing"]
    if not baseline_file.exists():
        return [f"{NAME}: {baseline_file.relative_to(root).as_posix()} is missing"]
    try:
        baseline = int(baseline_file.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        return [f"{NAME}: .corpus_count is not an integer"]
    live = _count(corpus)
    if live < baseline:
        return [
            f"{NAME}: regression corpus shrank: {live} test functions found, "
            f"baseline is {baseline}. If a removal is intended, lower "
            f".corpus_count in the same commit and explain why."
        ]
    return []


def make_bad_tree(tmp: Path) -> None:
    corpus = tmp / "backend" / "tests" / "regression"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / ".corpus_count").write_text("5\n", encoding="utf-8")
    (corpus / "test_only_one.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")


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
