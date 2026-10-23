"""WP-AB3: one free trial per business.

When a company starts a trial, keyed HMAC hashes of its GSTIN, PAN (from the GSTIN), owner phone and
owner email are stored in ``TrialFingerprint``. A later sign-up matches when its GSTIN or PAN hash
was seen, or its phone **and** email hashes were both seen, within ``TRIAL_DEDUPE_DAYS`` (365). A
match still gets an account: the trial is created already ended, so they can look around and pay,
and support code ``TRIAL_ALREADY_USED`` explains why. Staff can delete the fingerprint rows in
Django admin to allow a new trial.

The pepper is ``TRIAL_FINGERPRINT_PEPPER`` (comma-separated, newest first, so it can be rotated);
SECRET_KEY when unset (local only). No clear value is ever stored.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

TRIAL_ALREADY_USED = "TRIAL_ALREADY_USED"


def _peppers() -> list[bytes]:
    raw = (getattr(settings, "TRIAL_FINGERPRINT_PEPPER", "") or "").strip()
    keys = [k.strip() for k in raw.split(",") if k.strip()] or [settings.SECRET_KEY]
    return [k.encode() for k in keys]


def _digest(value: str, pepper: bytes) -> str:
    return hmac.new(pepper, value.encode(), hashlib.sha256).hexdigest()


def _values(*, gstin: str = "", phone: str = "", email: str = "") -> dict[str, str]:
    from accounts.otp_utils import normalize_e164

    out: dict[str, str] = {}
    g = (gstin or "").strip().upper()
    if len(g) == 15:
        out["gstin"] = g
        out["pan"] = g[2:12]
    if phone:
        try:
            out["phone"] = normalize_e164(phone)
        except ValueError:
            pass
    e = (email or "").strip().lower()
    if "@" in e:
        out["email"] = e
    return out


def _owner_contacts(company, owner=None) -> dict:
    return {
        "gstin": getattr(company, "gstin", "") or "",
        "phone": getattr(owner, "phone", "") or getattr(company, "phone", "") or "",
        "email": getattr(owner, "email", "") or getattr(company, "email", "") or "",
    }


def trial_used_before(company, owner=None) -> bool:
    from .models import TrialFingerprint

    values = _values(**_owner_contacts(company, owner))
    if not values:
        return False
    since = timezone.now() - timedelta(days=int(getattr(settings, "TRIAL_DEDUPE_DAYS", 365) or 365))
    seen: set[str] = set()
    for kind, value in values.items():
        digests = [_digest(value, p) for p in _peppers()]
        hit = (
            TrialFingerprint.objects.filter(kind=kind, digest__in=digests, created_at__gte=since)
            .exclude(company_id_hint=company.pk)
            .exists()
        )
        if hit:
            seen.add(kind)
    return bool(seen & {"gstin", "pan"}) or {"phone", "email"} <= seen


def record_trial(company, owner=None) -> None:
    """Store the fingerprint of a company that just started (or completed setup in) a trial."""
    from .models import TrialFingerprint

    pepper = _peppers()[0]
    for kind, value in _values(**_owner_contacts(company, owner)).items():
        digest = _digest(value, pepper)
        if not TrialFingerprint.objects.filter(kind=kind, digest=digest, company_id_hint=company.pk).exists():
            TrialFingerprint.objects.create(kind=kind, digest=digest, company_id_hint=company.pk)


@functools.lru_cache(maxsize=1)
def _disposable_domains() -> frozenset:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "core" / "data" / "disposable_email_domains.txt"
    try:
        return frozenset(line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return frozenset()


def disposable_email(email: str) -> bool:
    domain = (email or "").rsplit("@", 1)[-1].strip().lower()
    return bool(domain) and domain in _disposable_domains()
