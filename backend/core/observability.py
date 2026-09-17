"""Request correlation + hashed tenant ids for logs, Sentry, and Celery.

OG1-E1 / OG2: bind ``request_id`` and ``company_hash`` on a ContextVar so
access logs, exception envelopes, Sentry tags, and task headers share one id.
``company_hash`` is always derived (same 12-char SHA as access logs) — never
stored on ShopFloorEvent.
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("bizboard_request_id", default=None)
_company_hash: ContextVar[str | None] = ContextVar("bizboard_company_hash", default=None)


def hash_id(value) -> str:
    if value is None:
        return ""
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


def current_request_id() -> str | None:
    return _request_id.get()


def current_company_hash() -> str | None:
    return _company_hash.get()


def bind_request_context(*, request_id: str | None, company_hash: str | None = None) -> None:
    _request_id.set(request_id or None)
    _company_hash.set(company_hash or None)


def clear_request_context() -> None:
    _request_id.set(None)
    _company_hash.set(None)


def request_id_from_request(request) -> str | None:
    rid = getattr(request, "request_id", None)
    if rid:
        return str(rid)
    return current_request_id()


def apply_sentry_tags(*, request_id: str | None = None, company_hash: str | None = None, task_id: str | None = None) -> None:
    """Best-effort; never raises. No-op when sentry-sdk is not installed."""
    try:
        import sentry_sdk
    except ImportError:
        return
    rid = request_id if request_id is not None else current_request_id()
    ch = company_hash if company_hash is not None else current_company_hash()
    if rid:
        sentry_sdk.set_tag("request_id", rid)
    if ch:
        sentry_sdk.set_tag("company_hash", ch)
    if task_id:
        sentry_sdk.set_tag("task_id", str(task_id))


def sentry_before_send(event, hint):  # noqa: ARG001 — Sentry callback signature
    tags = event.setdefault("tags", {})
    rid = current_request_id()
    ch = current_company_hash()
    if rid and not tags.get("request_id"):
        tags["request_id"] = rid
    if ch and not tags.get("company_hash"):
        tags["company_hash"] = ch
    return event
