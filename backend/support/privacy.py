"""WP-CP2: the DPDP request register (docs/ops/DPDP_REQUESTS.md)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def _identity_check(user) -> str:
    """What was actually checked about the requester (the register is evidence, so no claim beyond it)."""
    if user is None:
        return ""
    try:
        from accounts.mfa_service import mfa_is_enabled

        return "Signed in; two-step on" if mfa_is_enabled(user) else "Signed in; no two-step"
    except Exception:  # noqa: BLE001
        return "Signed in"


def default_due():
    return timezone.now() + timedelta(days=int(getattr(settings, "DPDP_REQUEST_DUE_DAYS", 30) or 30))


def log_request(*, kind: str, requester: str, company=None, source: str = "SELF_SERVE", outcome: str = "",
                closed: bool = False, user=None):
    """Record one privacy request. Self-serve export and erasure call this, so every request is on
    the register even when the product handled it on its own. Never raises into the caller."""
    from .models import DataPrivacyRequest

    try:
        now = timezone.now()
        return DataPrivacyRequest.objects.create(
            kind=kind,
            source=source,
            requester=(requester or "")[:254],
            company_id_hint=getattr(company, "pk", None),
            due_at=default_due(),
            closed_at=now if closed else None,
            outcome=outcome,
            identity_check=_identity_check(user),
            handled_by=None,
        )
    except Exception:  # noqa: BLE001 - the register must not break the export or erasure itself
        import logging

        logging.getLogger(__name__).exception("Could not log a %s privacy request", kind)
        return None
