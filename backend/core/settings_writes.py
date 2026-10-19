"""SET-11b: shared write behaviour for settings endpoints.

Two guarantees the Settings screens rely on:

* **Optimistic lock.** An update that carries ``expected_updated_at`` (body field) or an
  ``X-Expected-Updated-At`` header is refused with 409 when the row has changed since that
  moment, so one owner cannot silently overwrite another owner's edit. Clients that send
  nothing keep today's last-write-wins behaviour, so adoption is per endpoint and safe.
* **Idempotent create.** When ``idempotent_scope`` is set, a POST with an ``Idempotency-Key``
  is applied once; a double-click or retry replays the first response.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils.dateparse import parse_datetime

from core.exceptions import BusinessRuleError, ConflictError
from core.idempotency import wrap_idempotent

# Serialised timestamps are rounded by clients and JSON, so compare to the millisecond.
_TOLERANCE = timedelta(milliseconds=1)


def _expected_updated_at(request) -> datetime | None:
    raw = None
    data = getattr(request, "data", None)
    if hasattr(data, "get"):
        raw = data.get("expected_updated_at")
    raw = raw or request.headers.get("X-Expected-Updated-At")
    if raw in (None, ""):
        return None
    parsed = parse_datetime(str(raw))
    if parsed is None:
        raise BusinessRuleError("expected_updated_at must be an ISO 8601 date-time.")
    return parsed


def check_expected_updated_at(request, instance) -> None:
    """Refuse (409) a write that started from an older version of ``instance``.

    No-op when the request carries no expected timestamp, so adoption is per client.
    """
    expected = _expected_updated_at(request)
    if expected is None:
        return
    current = getattr(instance, "updated_at", None)
    if current is not None and abs(current - expected) > _TOLERANCE:
        raise ConflictError(
            "This setting was changed after you opened it. Reload to see the latest values.",
            code="SETTINGS_STALE",
        )


class SettingsWriteMixin:
    """Mix into a ModelViewSet (before the viewset base class)."""

    #: Set to a short unique name to make POST idempotent for this endpoint.
    idempotent_scope: str = ""

    def update(self, request, *args, **kwargs):
        if _expected_updated_at(request) is not None:
            check_expected_updated_at(request, self.get_object())
        return super().update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if not self.idempotent_scope:
            return super().create(request, *args, **kwargs)
        return wrap_idempotent(
            request=request,
            company=self.company,
            scope=self.idempotent_scope,
            build=lambda: super(SettingsWriteMixin, self).create(request, *args, **kwargs),
        )
