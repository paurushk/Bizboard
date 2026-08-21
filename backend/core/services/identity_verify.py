"""PAN / UDYAM verification — format-first, live portal optional (Phase 7.4).

Soft-fail: a failed or pending lookup never blocks company save. Null provider
never stamps VALID / verified_at (same honesty rule as GSTIN).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from core.services.audit import AuditService
from core.validators import PAN_RE, UDYAM_RE


@dataclass
class IdentityLookupResult:
    number: str
    legal_name: str
    status: str  # VALID | INVALID | UNVERIFIED
    kind: str  # PAN | UDYAM
    raw: dict


class NullIdentityProvider:
    def lookup_pan(self, pan: str) -> IdentityLookupResult:
        pan = (pan or "").strip().upper()
        if not PAN_RE.match(pan):
            return IdentityLookupResult(
                number=pan,
                legal_name="",
                status="INVALID",
                kind="PAN",
                raw={"provider": "null", "error": "invalid_format"},
            )
        return IdentityLookupResult(
            number=pan,
            legal_name="",
            status="UNVERIFIED",
            kind="PAN",
            raw={"provider": "null", "note": "format_ok_not_live_verified"},
        )

    def lookup_udyam(self, udyam: str) -> IdentityLookupResult:
        udyam = (udyam or "").strip().upper()
        if not UDYAM_RE.match(udyam):
            return IdentityLookupResult(
                number=udyam,
                legal_name="",
                status="INVALID",
                kind="UDYAM",
                raw={"provider": "null", "error": "invalid_format"},
            )
        return IdentityLookupResult(
            number=udyam,
            legal_name="",
            status="UNVERIFIED",
            kind="UDYAM",
            raw={"provider": "null", "note": "format_ok_not_live_verified"},
        )


def get_identity_provider():
    from django.conf import settings

    name = (getattr(settings, "IDENTITY_PROVIDER", "null") or "null").strip().lower()
    if name in ("http", "gsp") or (getattr(settings, "IDENTITY_SANDBOX_BASE_URL", "") or "").strip():
        return HttpIdentityProvider()
    return NullIdentityProvider()


class HttpIdentityProvider:
    """Optional HTTP PAN/UDYAM lookup. Fail-closed: missing URL or HTTP error → UNVERIFIED."""

    def _get(self, path: str) -> dict | None:
        from django.conf import settings
        import json
        import urllib.error
        import urllib.request

        base = (getattr(settings, "IDENTITY_SANDBOX_BASE_URL", "") or "").rstrip("/")
        if not base:
            return None
        try:
            req = urllib.request.Request(f"{base}{path}", method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return {"error": "lookup_failed"}

    def lookup_pan(self, pan: str) -> IdentityLookupResult:
        pan = (pan or "").strip().upper()
        if not PAN_RE.match(pan):
            return IdentityLookupResult(
                number=pan, legal_name="", status="INVALID", kind="PAN",
                raw={"provider": "http", "error": "invalid_format"},
            )
        payload = self._get(f"/pan/{pan}")
        if not payload or payload.get("error"):
            return IdentityLookupResult(
                number=pan, legal_name="", status="UNVERIFIED", kind="PAN",
                raw={"provider": "http", "error": (payload or {}).get("error") or "no_endpoint"},
            )
        status = (payload.get("status") or "UNVERIFIED").upper()
        if status == "VALID":
            # Only certified providers may stamp VALID; sandbox URL is never that.
            from django.conf import settings

            env = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
            if env in ("production", "staging"):
                status = "UNVERIFIED"
        return IdentityLookupResult(
            number=pan,
            legal_name=payload.get("legal_name") or payload.get("name") or "",
            status=status if status in ("VALID", "INVALID", "UNVERIFIED") else "UNVERIFIED",
            kind="PAN",
            raw={"provider": "http", **payload},
        )

    def lookup_udyam(self, udyam: str) -> IdentityLookupResult:
        udyam = (udyam or "").strip().upper()
        if not UDYAM_RE.match(udyam):
            return IdentityLookupResult(
                number=udyam, legal_name="", status="INVALID", kind="UDYAM",
                raw={"provider": "http", "error": "invalid_format"},
            )
        payload = self._get(f"/udyam/{udyam}")
        if not payload or payload.get("error"):
            return IdentityLookupResult(
                number=udyam, legal_name="", status="UNVERIFIED", kind="UDYAM",
                raw={"provider": "http", "error": (payload or {}).get("error") or "no_endpoint"},
            )
        status = (payload.get("status") or "UNVERIFIED").upper()
        if status == "VALID":
            from django.conf import settings

            env = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
            if env in ("production", "staging"):
                status = "UNVERIFIED"
        return IdentityLookupResult(
            number=udyam,
            legal_name=payload.get("enterprise_name") or payload.get("legal_name") or payload.get("name") or "",
            status=status if status in ("VALID", "INVALID", "UNVERIFIED") else "UNVERIFIED",
            kind="UDYAM",
            raw={"provider": "http", **payload},
        )


def apply_pan_verification(company, result: IdentityLookupResult, *, user=None):
    is_null = (result.raw or {}).get("provider") == "null" or result.status == "UNVERIFIED"
    status = result.status
    if is_null and status == "VALID":
        status = "UNVERIFIED"
    company.pan = result.number or company.pan
    company.pan_verification_status = status
    company.pan_legal_name = result.legal_name
    company.pan_raw_payload = result.raw
    update_fields = ["pan", "pan_verification_status", "pan_legal_name", "pan_raw_payload"]
    if status == "VALID" and not is_null:
        company.pan_verified_at = timezone.now()
        update_fields.append("pan_verified_at")
    elif company.pan_verified_at is not None:
        company.pan_verified_at = None
        update_fields.append("pan_verified_at")
    if hasattr(company, "updated_at"):
        update_fields.append("updated_at")
    company.save(update_fields=update_fields)
    if user is not None:
        AuditService.log(
            company=company,
            user=user,
            action="UPDATE",
            entity_type="company",
            entity_id=company.pk,
            description="pan.lookup",
        )
    return company


def apply_udyam_verification(company, result: IdentityLookupResult, *, user=None):
    is_null = (result.raw or {}).get("provider") == "null" or result.status == "UNVERIFIED"
    status = result.status
    if is_null and status == "VALID":
        status = "UNVERIFIED"
    company.udyam = result.number or company.udyam
    company.udyam_verification_status = status
    company.udyam_enterprise_name = result.legal_name
    company.udyam_raw_payload = result.raw
    update_fields = [
        "udyam",
        "udyam_verification_status",
        "udyam_enterprise_name",
        "udyam_raw_payload",
    ]
    if status == "VALID" and not is_null:
        company.udyam_verified_at = timezone.now()
        update_fields.append("udyam_verified_at")
    elif company.udyam_verified_at is not None:
        company.udyam_verified_at = None
        update_fields.append("udyam_verified_at")
    if hasattr(company, "updated_at"):
        update_fields.append("updated_at")
    company.save(update_fields=update_fields)
    if user is not None:
        AuditService.log(
            company=company,
            user=user,
            action="UPDATE",
            entity_type="company",
            entity_id=company.pk,
            description="udyam.lookup",
        )
    return company
