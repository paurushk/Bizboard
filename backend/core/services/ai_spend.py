"""WP-I1: one spend counter in front of every model call.

Every path that calls a model — the agents gateway (``llm_gateway.chat``), the assistant and
ops copilot (``llm.chat_with_tools``) and bill extraction (``llm.extract_purchase_bill``) — goes
through ``guarded(estimate)``. It reserves the estimated tokens **before** the call against two
daily counters (this company, and the whole platform), then settles to the real usage after.
Reserving first means concurrent calls cannot overshoot a cap.

Counters live in the Django cache (Redis in staging/production), keyed by IST date, 48 h TTL.
If the cache is down the call is refused (``AI_SPEND_FAIL_CLOSED``, default on): an outage must
not become unlimited spend. ``AI_GLOBAL_KILL`` refuses every call immediately. The durable record
stays in ``AiUsageLedger`` (Django admin), written by each caller as before.

Callers name the company with ``charging(company_id)``; a call outside it is charged to the
platform counter only (the ops copilot).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from core.exceptions import BusinessRuleError

_company: ContextVar[int | None] = ContextVar("ai_spend_company", default=None)
_TTL = 48 * 60 * 60


class AiSpendBlocked(BusinessRuleError):
    """The model call was refused before it was made (cap reached, kill switch, counter down)."""


@dataclass
class Reservation:
    company_id: int | None
    units: int
    day: str
    actual: int | None = None


@contextmanager
def charging(company_id):
    token = _company.set(int(company_id) if company_id is not None else None)
    try:
        yield
    finally:
        _company.reset(token)


def current_company_id() -> int | None:
    return _company.get()


def _keys(day: str, company_id: int | None) -> list[tuple[str, int]]:
    keys = [(f"ai:spend:{day}:platform", int(getattr(settings, "AI_PLATFORM_DAILY_TOKEN_CAP", 0) or 0))]
    if company_id is not None:
        keys.append((f"ai:spend:{day}:c:{company_id}", int(getattr(settings, "AI_TENANT_DAILY_TOKEN_CAP", 0) or 0)))
    return keys


def _incr(key: str, delta: int) -> int:
    from django.core.cache import cache

    cache.add(key, 0, _TTL)
    return int(cache.incr(key, delta))


def reserve(estimate: int) -> Reservation:
    if getattr(settings, "AI_GLOBAL_KILL", False):
        raise AiSpendBlocked("AI features are switched off for the platform right now.", code="AI_GLOBAL_KILL")
    units = max(1, int(estimate))
    company_id = current_company_id()
    day = timezone.localdate().isoformat()
    done: list[str] = []
    try:
        for key, cap in _keys(day, company_id):
            total = _incr(key, units)
            done.append(key)
            if cap and total > cap:
                for k in done:
                    _incr(k, -units)
                who = "this company" if key.endswith(f":c:{company_id}") else "the platform"
                raise AiSpendBlocked(f"Today's AI limit for {who} is reached. It resets tomorrow.", code="AI_SPEND_CAP")
    except AiSpendBlocked:
        raise
    except Exception as exc:  # noqa: BLE001 - counter store down
        for k in done:
            try:
                _incr(k, -units)
            except Exception:  # noqa: BLE001
                pass
        if getattr(settings, "AI_SPEND_FAIL_CLOSED", True):
            raise AiSpendBlocked("AI is unavailable right now. Try again in a few minutes.", code="AI_SPEND_UNAVAILABLE") from exc
    return Reservation(company_id=company_id, units=units, day=day)


def settle(res: Reservation) -> None:
    """Replace the estimate with the real usage (never raises)."""
    if res.actual is None or res.actual == res.units:
        return
    delta = int(res.actual) - res.units
    for key, _cap in _keys(res.day, res.company_id):
        try:
            _incr(key, delta)
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def guarded(estimate: int):
    """Reserve ``estimate`` tokens, run the call, settle to ``res.actual`` (set it from the response)."""
    res = reserve(estimate)
    try:
        yield res
    finally:
        settle(res)


def used_today(company_id: int | None = None) -> int:
    from django.core.cache import cache

    day = timezone.localdate().isoformat()
    key = f"ai:spend:{day}:c:{company_id}" if company_id is not None else f"ai:spend:{day}:platform"
    try:
        return int(cache.get(key) or 0)
    except Exception:  # noqa: BLE001
        return 0


def would_allow(company_id: int | None, estimate: int = 1) -> bool:
    """A cheap pre-check (no reservation) so callers can degrade instead of failing mid-way."""
    if getattr(settings, "AI_GLOBAL_KILL", False):
        return False
    day = timezone.localdate().isoformat()
    for key, cap in _keys(day, company_id):
        if not cap:
            continue
        from django.core.cache import cache

        try:
            if int(cache.get(key) or 0) + estimate > cap:
                return False
        except Exception:  # noqa: BLE001
            return not getattr(settings, "AI_SPEND_FAIL_CLOSED", True)
    return True
