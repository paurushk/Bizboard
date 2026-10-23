"""Read-only client for the error tracker (self-hosted GlitchTip, or Sentry: same API).

Used by staff tooling only: the Django admin errors page, "matching errors" links
on support tickets, and the watcher task that pages when the tracker itself is
unreachable. Nothing here runs on a customer request path.

Settings (all empty = feature off, every function degrades to None / not configured):
    ERROR_TRACKER_API_URL  base the API host calls, e.g. http://glitchtip:8000 (stack network)
    ERROR_TRACKER_UI_URL   base people open in a browser; defaults to the API URL
    ERROR_TRACKER_ORG      organisation slug (default "bizboard")
    ERROR_TRACKER_TOKEN    API token with read scopes (glitchtip-init creates it)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
_REQUEST_ID_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


@dataclass
class IssuesResult:
    ok: bool
    issues: list[dict] = field(default_factory=list)
    error: str = ""


def _api_base() -> str:
    return (getattr(settings, "ERROR_TRACKER_API_URL", "") or "").strip().rstrip("/")


def _ui_base() -> str:
    return (getattr(settings, "ERROR_TRACKER_UI_URL", "") or "").strip().rstrip("/") or _api_base()


def _org() -> str:
    return (getattr(settings, "ERROR_TRACKER_ORG", "") or "").strip() or "bizboard"


def _token() -> str:
    return (getattr(settings, "ERROR_TRACKER_TOKEN", "") or "").strip()


def is_configured() -> bool:
    return bool(_api_base() and _token())


def request_id_query(request_id: str) -> str | None:
    """Tracker search for one request id, or None when it is not a plain id.

    Both the API (core.observability.sentry_before_send) and the SPA tag every
    event with ``request_id``, which is the Support ID people quote.
    """
    rid = (request_id or "").strip()
    if not rid or len(rid) > 64 or not set(rid) <= _REQUEST_ID_SAFE:
        return None
    return f"request_id:{rid}"


def search_url(query: str) -> str | None:
    """Link a person can open to see the tracker's issues for ``query``."""
    base = _ui_base()
    if not base or not query:
        return None
    org = quote(_org(), safe="")
    if "sentry.io" in base:
        return f"{base}/organizations/{org}/issues/?{urlencode({'query': query})}"
    return f"{base}/{org}/issues?{urlencode({'query': query})}"


def request_id_url(request_id: str) -> str | None:
    query = request_id_query(request_id)
    return search_url(query) if query else None


def _get(path: str, params: dict | None = None) -> requests.Response:
    return requests.get(
        f"{_api_base()}/api/0/organizations/{quote(_org(), safe='')}/{path}",
        params=params,
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=TIMEOUT_SECONDS,
    )


def issue_url(issue_id) -> str:
    """Link to one issue, built from the UI URL people actually use.

    Not the API's ``permalink``: GlitchTip 6 puts the project slug where its UI expects the
    organisation (a dead link), and both trackers build it from their own configured
    domain, which is not the address staff reach the UI on through an SSH tunnel.
    """
    base, issue = _ui_base(), str(issue_id or "")
    if not base or not issue.isdigit():
        return ""
    org = quote(_org(), safe="")
    if "sentry.io" in base:
        return f"{base}/organizations/{org}/issues/{issue}/"
    return f"{base}/{org}/issues/{issue}"


def fetch_issues(query: str = "is:unresolved", limit: int = 25) -> IssuesResult:
    if not is_configured():
        return IssuesResult(ok=False, error="not configured")
    try:
        resp = _get("issues/", {"query": query, "limit": max(1, min(limit, 100))})
    except requests.RequestException as exc:
        logger.warning("error tracker: issues fetch failed: %s", exc.__class__.__name__)
        return IssuesResult(ok=False, error=f"unreachable ({exc.__class__.__name__})")
    if resp.status_code != 200:
        return IssuesResult(ok=False, error=f"HTTP {resp.status_code}")
    try:
        rows = resp.json()
    except ValueError:
        return IssuesResult(ok=False, error="unreadable response")
    if not isinstance(rows, list):
        return IssuesResult(ok=False, error="unexpected response")
    issues = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        project = row.get("project") if isinstance(row.get("project"), dict) else {}
        issues.append(
            {
                "short_id": str(row.get("shortId") or row.get("id") or ""),
                "title": str(row.get("title") or "")[:200],
                "culprit": str(row.get("culprit") or "")[:200],
                "level": str(row.get("level") or ""),
                "project": str(project.get("slug") or ""),
                "count": str(row.get("count") or ""),
                "first_seen": str(row.get("firstSeen") or ""),
                "last_seen": str(row.get("lastSeen") or ""),
                "url": issue_url(row.get("id")),
            }
        )
    return IssuesResult(ok=True, issues=issues)


def check_reachable() -> tuple[bool, str]:
    """(reachable, detail). Authenticated, so a wrong token reads as a failure too."""
    if not is_configured():
        return False, "not configured"
    try:
        resp = _get("")
    except requests.RequestException as exc:
        return False, f"unreachable ({exc.__class__.__name__})"
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"
    return True, "ok"
