"""PAN / UDYAM verification — format-first, live portal optional (Phase 7.4).

Soft-fail: a failed or pending lookup never blocks company save. Null provider
never stamps VALID / verified_at (same honesty rule as GSTIN).
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
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


class _RedirectRefused(urllib.request.HTTPError):
    """Raised by the opener so a 302 cannot hop to a link-local address."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = newurl or getattr(req, "full_url", "") or ""
        raise _RedirectRefused(url, code, "redirect refused", headers, fp)


def _unwrap(ip: ipaddress.IPv4Address | ipaddress.IPv6Address):
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _address_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    ip = _unwrap(ip)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _localhost_exception(host: str) -> bool:
    from django.conf import settings

    env = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
    if env in ("production", "staging"):
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _pin_target(url: str) -> tuple[str, str, int, str] | dict:
    """Return (hostname, ip, port, scheme) or an error dict. Does not connect."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").strip("[]")
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("https", "http") or not host:
        return {"error": "lookup_failed"}
    if scheme == "http" and not _localhost_exception(host):
        return {"error": "lookup_failed"}
    if scheme == "https" and _address_blocked_host(host) and not _localhost_exception(host):
        return {"error": "lookup_failed"}
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return {"error": "lookup_failed"}
    ips = []
    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            return {"error": "lookup_failed"}
        if _address_blocked(ip) and not _localhost_exception(host):
            return {"error": "lookup_failed"}
        ips.append(raw)
    if not ips:
        return {"error": "lookup_failed"}
    return host, ips[0], port, scheme


def _address_blocked_host(host: str) -> bool:
    try:
        return _address_blocked(ipaddress.ip_address(host))
    except ValueError:
        return False


def open_pinned_url(url: str, timeout: int = 8) -> str:
    """GET ``url`` at the resolved address. Refuses redirects and private targets.

    Returns the response body text, or raises ``ValueError`` / ``urllib.error.URLError``.
    The TCP connection uses the address from ``getaddrinfo``, not a second lookup.
    """
    pinned = _pin_target(url)
    if isinstance(pinned, dict):
        raise ValueError("lookup_failed")
    host, ip, port, scheme = pinned
    if scheme == "https":
        context = ssl.create_default_context()

        class Conn(http.client.HTTPSConnection):
            def connect(self):
                raw = socket.create_connection((ip, port), self.timeout)
                self.sock = self._context.wrap_socket(raw, server_hostname=host)

        handler = urllib.request.HTTPSHandler(context=context)
        opener = urllib.request.build_opener(_NoRedirect, handler)

        def https_open(req):
            return handler.do_open(Conn, req)

        handler.https_open = https_open  # type: ignore[method-assign]
    else:

        class Conn(http.client.HTTPConnection):
            def connect(self):
                self.sock = socket.create_connection((ip, port), self.timeout)

        handler = urllib.request.HTTPHandler()
        opener = urllib.request.build_opener(_NoRedirect, handler)

        def http_open(req):
            return handler.do_open(Conn, req)

        handler.http_open = http_open  # type: ignore[method-assign]
    req = urllib.request.Request(url, method="GET", headers={"Host": host})
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


class HttpIdentityProvider:
    """Optional HTTP PAN/UDYAM lookup. Fail-closed: missing URL or HTTP error → UNVERIFIED."""

    def _get(self, path: str) -> dict | None:
        from django.conf import settings
        import json

        base = (getattr(settings, "IDENTITY_SANDBOX_BASE_URL", "") or "").rstrip("/")
        if not base:
            return None
        url = f"{base}{path}"
        try:
            body = open_pinned_url(url, timeout=8)
            return json.loads(body or "{}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
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
