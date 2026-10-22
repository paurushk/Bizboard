from django.http import Http404

from core.services.feature_flags import build_feature_flags


def assert_legacy_import_enabled(company) -> None:
    """WP-GR1b: Busy / Vyapar / Marg import, granted per pilot company like Tally (GR1a)."""
    flags = build_feature_flags(company=company)
    if not flags.get("ENABLE_LEGACY_IMPORT"):
        raise Http404()


def assert_tally_enabled(company) -> None:
    flags = build_feature_flags(company=company)
    if not flags.get("ENABLE_TALLY"):
        raise Http404()
