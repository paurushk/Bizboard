"""GSTIN live verification — pluggable provider (Null / Sandbox)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.validators import GSTIN_RE


@dataclass
class GstinLookupResult:
    gstin: str
    legal_name: str
    status: str  # VALID | INVALID | CANCELLED | SUSPENDED | UNVERIFIED
    state_code: str
    taxpayer_type: str
    raw: dict


class GstinProvider(Protocol):
    def lookup(self, gstin: str) -> GstinLookupResult: ...


class NullGstinProvider:
    """Dev/default: format-valid → UNVERIFIED (never claim VALID without a real GSP)."""

    def lookup(self, gstin: str) -> GstinLookupResult:
        gstin = (gstin or "").strip().upper()
        if not GSTIN_RE.match(gstin):
            return GstinLookupResult(
                gstin=gstin,
                legal_name="",
                status="INVALID",
                state_code="",
                taxpayer_type="",
                raw={"provider": "null", "error": "invalid_format"},
            )
        return GstinLookupResult(
            gstin=gstin,
            legal_name="",
            status="UNVERIFIED",
            state_code=gstin[:2],
            taxpayer_type="",
            raw={"provider": "null", "note": "format_ok_not_live_verified"},
        )


def get_gstin_provider() -> GstinProvider:
    from django.conf import settings

    name = (getattr(settings, "GSTIN_PROVIDER", "null") or "null").strip().lower()
    if name in ("http", "gsp") or getattr(settings, "GSP_HTTP_SANDBOX", False):
        return HttpGstinProvider()
    return NullGstinProvider()


class HttpGstinProvider:
    """Wave 16C: optional HTTP GSTIN lookup against GSP_SANDBOX_BASE_URL."""

    def lookup(self, gstin: str) -> GstinLookupResult:
        from django.conf import settings
        import json
        import urllib.error
        import urllib.request

        gstin = (gstin or "").strip().upper()
        if not GSTIN_RE.match(gstin):
            return GstinLookupResult(
                gstin=gstin, legal_name="", status="INVALID", state_code="", taxpayer_type="",
                raw={"provider": "http", "error": "invalid_format"},
            )
        base = (getattr(settings, "GSP_SANDBOX_BASE_URL", "") or "").rstrip("/")
        if not base:
            return NullGstinProvider().lookup(gstin)
        try:
            from core.services.gsp_adapters import assert_safe_outbound_url

            url = f"{base}/gstin/{gstin}"
            assert_safe_outbound_url(url)  # B7-015
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode() or "{}")
            status = str(raw.get("status") or "UNVERIFIED").upper()
            if status == "VALID" and not raw.get("legal_name"):
                status = "UNVERIFIED"
            return GstinLookupResult(
                gstin=gstin,
                legal_name=str(raw.get("legal_name") or ""),
                status=status,
                state_code=gstin[:2],
                taxpayer_type=str(raw.get("taxpayer_type") or ""),
                raw={**raw, "provider": "http"},
            )
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, BusinessRuleError):
            return NullGstinProvider().lookup(gstin)


def apply_verification(target, result: GstinLookupResult, *, user=None, company=None):
    """
    Persist lookup outcome honestly.

    BB-000285/225: Null / non-live results must never set status VALID or
    gstin_verified_at (that timestamp means a live portal verification).
    BB-000734: sandbox/HTTP VALID must not stamp gstin_verified_at in
    production/staging unless GSP_CERTIFIED.
    """
    from django.conf import settings

    provider = (result.raw or {}).get("provider")
    is_null = provider == "null" or result.status == "UNVERIFIED"
    # Defense: Null provider must never write VALID even if misconfigured upstream.
    status = result.status
    if is_null and status == "VALID":
        status = "UNVERIFIED"

    target.gstin_verification_status = status
    target.gstin_legal_name = result.legal_name
    target.gstin_raw_payload = result.raw
    update_fields = [
        "gstin_verification_status",
        "gstin_legal_name",
        "gstin_raw_payload",
    ]

    may_stamp_verified = status == "VALID" and not is_null
    if may_stamp_verified:
        env = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
        certified = getattr(settings, "GSP_CERTIFIED", False) is True
        # Sandbox/HTTP (and any uncertified path) cannot claim live verify in paid envs.
        if env in ("production", "staging") and not certified:
            may_stamp_verified = False

    if may_stamp_verified:
        target.gstin_verified_at = timezone.now()
        update_fields.append("gstin_verified_at")
    else:
        # Clear any stale verified_at from a prior false claim.
        if getattr(target, "gstin_verified_at", None) is not None:
            target.gstin_verified_at = None
            update_fields.append("gstin_verified_at")

    if hasattr(target, "updated_at"):
        update_fields.append("updated_at")
    target.save(update_fields=update_fields)
    if company is not None and user is not None:
        AuditService.log(
            company=company,
            user=user,
            action="UPDATE",
            entity_type=target.__class__.__name__.lower(),
            entity_id=getattr(target, "pk", None),
            description="gstin.lookup" if is_null or status != "VALID" else "gstin.verified",
            metadata={
                "gstin": result.gstin,
                "status": status,
                "legal_name": result.legal_name,
                "live_verified": may_stamp_verified,
            },
        )
    return result
