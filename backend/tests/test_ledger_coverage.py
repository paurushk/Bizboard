"""WP-F1: the ledger coverage registry is complete, enforced, and its generated map is current."""

from pathlib import Path

import pytest
from django.test import override_settings

from accounting.coverage import NOT_POSTED, POSTING_SOURCES, ledger_gaps, render_markdown

ROOT = Path(__file__).resolve().parents[2]


def test_the_generated_map_is_current():
    path = ROOT / "docs" / "accounting" / "LEDGER_COVERAGE_MAP.md"
    assert path.exists(), "run: python manage.py ledger_coverage_map --write"
    assert path.read_text(encoding="utf-8") == render_markdown(), (
        "docs/accounting/LEDGER_COVERAGE_MAP.md is stale; run: python manage.py ledger_coverage_map --write"
    )


def test_every_registered_source_names_a_real_module_and_invariants():
    from core.invariants import registered

    REGISTRY = registered()

    for st, src in POSTING_SOURCES.items():
        assert (ROOT / "backend" / src.posted_by).exists(), f"{st}: {src.posted_by} missing"
        for key in src.invariants:
            assert key in REGISTRY, f"{st}: unknown invariant {key}"
    assert NOT_POSTED


@pytest.mark.django_db
def test_an_unregistered_source_cannot_post_under_strict_mode(tenant_a):
    from accounting.services import PostingService

    with pytest.raises(AssertionError, match="not in accounting/coverage.py"):
        PostingService.post(
            company=tenant_a.company, source_type="BRAND_NEW_DOC", source_id=1, purpose="POST",
            entry_date=None, lines=[],
        )


@pytest.mark.django_db
def test_outside_strict_mode_it_is_only_logged(tenant_a, caplog):
    from accounting.services import PostingService

    with override_settings(LEDGER_REGISTRY_STRICT=False):
        tenant_a.company.accounting_enabled = False
        tenant_a.company.post_ledger = False  # nothing posts, so only the registry check runs
        assert PostingService.post(
            company=tenant_a.company, source_type="BRAND_NEW_DOC_2", source_id=1, purpose="POST",
            entry_date=None, lines=[],
        ) is None
    assert "not in the ledger coverage registry" in caplog.text


@pytest.mark.django_db
def test_flags_that_are_off_show_up_as_ledger_gaps(tenant_a, monkeypatch):
    gated = {s.flag for s in POSTING_SOURCES.values() if s.flag}
    monkeypatch.setattr("core.services.feature_flags.flag_enabled", lambda company, key: False)
    gaps = ledger_gaps(tenant_a.company)
    assert {g["flag"] for g in gaps} == gated
    assert all(g["covers"] and g["note"] for g in gaps)
    monkeypatch.setattr("core.services.feature_flags.flag_enabled", lambda company, key: True)
    assert ledger_gaps(tenant_a.company) == []
