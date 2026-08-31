"""A-05: golden-month harness. Skips unless a CA CSV is present."""

from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "pilot" / "fixtures" / "ca_golden_month.csv"

pytestmark = pytest.mark.django_db


@pytest.mark.skipif(not FIXTURE.exists(), reason="CA golden-month CSV not present")
def test_golden_month_csv_has_header():
    text = FIXTURE.read_text(encoding="utf-8")
    first = (text.splitlines() or [""])[0].lower()
    assert "account" in first or "ledger" in first or "code" in first
