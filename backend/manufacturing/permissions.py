from django.http import Http404

from core.services.feature_flags import build_feature_flags


def assert_manufacturing_enabled(company) -> None:
    flags = build_feature_flags(company=company)
    if not flags.get("ENABLE_MANUFACTURING"):
        raise Http404()
