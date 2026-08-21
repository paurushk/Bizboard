from django.http import Http404

from core.services.feature_flags import build_feature_flags


def assert_gstr_enabled(company) -> None:
    flags = build_feature_flags(company=company)
    if not flags.get("ENABLE_GSTR"):
        raise Http404()
