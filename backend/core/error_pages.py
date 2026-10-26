"""WP-1 (ZAP 100001): API paths answer errors in JSON, like every other API response.

Without these, an unknown ``/api/...`` path (or an unhandled error outside DRF) gets Django's HTML
page, which clients cannot parse and which scanners flag. Other paths keep Django's own pages.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.views import defaults


def _is_api(request) -> bool:
    return request.path.startswith("/api/")


def not_found(request, exception=None):
    if _is_api(request):
        return JsonResponse(
            {"success": False, "error": {"code": "not_found", "message": "Not found.", "details": {}}},
            status=404,
        )
    return defaults.page_not_found(request, exception)


def server_error(request):
    if _is_api(request):
        return JsonResponse(
            {"success": False, "error": {"code": "server_error", "message": "Something went wrong.", "details": {}}},
            status=500,
        )
    return defaults.server_error(request)
