"""IRP / e-Way / GSTR filing adapters — Wave 16C / Sprint E (BB-000624).

- Hash sandbox (default in test/dev)
- HTTP sandbox when GSP_HTTP_SANDBOX=1 + GSP_SANDBOX_BASE_URL
- Live HTTP when GSP_LIVE_ENABLED + GSP_CERTIFIED + credentials + GSP_LIVE_BASE_URL
- Never invents production IRNs / SignedQRCode / e-Way validity without a provider response
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.exceptions import BusinessRuleError
from core.services.gsp_secrets import decrypt_gsp_credentials

logger = logging.getLogger(__name__)

_VALID_PROVIDERS = frozenset({"cleartax", "mastergst", "custom"})
_NIC_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %I:%M:%S %p",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d",
)


@dataclass
class IrnResult:
    irn: str
    ack_no: str
    ack_date: datetime
    einvoice_qr: str
    raw: dict


@dataclass
class EwayResult:
    eway_bill_no: str
    eway_valid_upto: datetime
    raw: dict


@runtime_checkable
class IrpAdapter(Protocol):
    def submit(self, payload: dict) -> IrnResult: ...
    def cancel(self, irn: str, cnl_rsn: str = "1", cnl_rem: str = "Cancelled") -> dict: ...


@runtime_checkable
class EwayAdapter(Protocol):
    def submit(self, payload: dict) -> EwayResult: ...
    def cancel(self, eway_bill_no: str) -> dict: ...


@runtime_checkable
class GstrFilingAdapter(Protocol):
    def upload_gstr1(self, payload: dict) -> dict: ...
    def upload_gstr3b(self, payload: dict) -> dict: ...
    def fetch_gstr2b(self, period: str) -> dict: ...


def _django_env() -> str:
    return (getattr(settings, "DJANGO_ENV", "development") or "development").strip().lower()


def _live_enabled() -> bool:
    return getattr(settings, "GSP_LIVE_ENABLED", False) is True


def _gsp_certified() -> bool:
    return getattr(settings, "GSP_CERTIFIED", False) is True


_PLACEHOLDER_SECRETS = frozenset({
    "",
    "aaaa",
    "aaaaaaaa",
    "placeholder",
    "test",
    "changeme",
    "your-api-key",
    "secret",
    "apikey",
    "api-key",
})


def reject_placeholder_gsp_credentials(creds: dict | None) -> None:
    """B-01: all-A / demo secrets must never reach live HTTP."""
    if not creds:
        raise BusinessRuleError("Live GSP credentials are empty.")
    for value in creds.values():
        raw = str(value or "").strip()
        if not raw:
            continue
        low = raw.lower()
        if low in _PLACEHOLDER_SECRETS or (len(raw) >= 4 and set(raw.lower()) == {"a"}):
            raise BusinessRuleError("Placeholder GSP secrets are rejected. Use named-provider credentials.")


def _http_sandbox_enabled() -> bool:
    return getattr(settings, "GSP_HTTP_SANDBOX", False) is True


def resolve_gsp_provider(company=None) -> str:
    """cleartax | mastergst | custom — settings first, then company.gsp_provider."""
    raw = (getattr(settings, "GSP_PROVIDER", "") or "").strip().lower()
    if raw in _VALID_PROVIDERS:
        return raw
    if company is not None:
        company_raw = (getattr(company, "gsp_provider", None) or "").strip().lower()
        if company_raw in _VALID_PROVIDERS:
            return company_raw
    return "custom"


def parse_provider_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value
    text = str(value).strip()
    if text.endswith("Z") and "+00:00" not in text:
        text = text[:-1] + "+00:00"
    parsed = parse_datetime(text)
    if parsed is not None:
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    for fmt in _NIC_DT_FORMATS:
        try:
            dt = datetime.strptime(str(value).strip(), fmt)
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except ValueError:
            continue
    return None


def parse_eway_valid_upto(raw: dict, *, allow_default: bool = False) -> datetime:
    """Parse validUpto from a provider body. Do not invent dates on live/HTTP.

    Hash sandbox may pass ``allow_default=True`` for a documented +1 day fallback
    only when the (synthetic) response has no validity field.
    """
    if not isinstance(raw, dict):
        raw = {}
    nested = raw.get("Data") or raw.get("data") or raw
    if isinstance(nested, list) and nested:
        nested = nested[0]
    if not isinstance(nested, dict):
        nested = raw
    candidates = (
        nested.get("validUpto"),
        nested.get("ValidUpto"),
        nested.get("valid_upto"),
        nested.get("ewayBillValidUpto"),
        nested.get("eway_valid_upto"),
        raw.get("validUpto"),
        raw.get("ValidUpto"),
        raw.get("valid_upto"),
        raw.get("ewayBillValidUpto"),
        raw.get("eway_valid_upto"),
    )
    for val in candidates:
        parsed = parse_provider_datetime(val)
        if parsed is not None:
            return parsed
    if allow_default:
        # Documented hash-sandbox fallback only — never used by live/HTTP adapters.
        return timezone.now() + timedelta(days=1)
    raise BusinessRuleError("e-Way response missing validUpto.")


def verify_signed_qr_ack(irn: str, ack_no: str, einvoice_qr: str) -> None:
    """Require Irn + AckNo + SignedQRCode before GENERATED. Optionally match QR irn."""
    irn = (irn or "").strip()
    ack_no = (ack_no or "").strip()
    qr = (einvoice_qr or "").strip() if isinstance(einvoice_qr, str) else ""
    if not irn:
        raise BusinessRuleError("IRP response missing Irn.")
    if not ack_no:
        raise BusinessRuleError("IRP response missing AckNo.")
    if not qr:
        raise BusinessRuleError("IRP response missing SignedQRCode.")
    try:
        data = json.loads(qr)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(data, dict):
        return
    qr_irn = str(data.get("irn") or data.get("Irn") or "").strip()
    if qr_irn and qr_irn != irn:
        raise BusinessRuleError("SignedQRCode irn does not match Irn.")


def plain_gsp_error(raw: str) -> str:
    """Partner codes become one sentence a booker and a CA can both read."""
    text = (raw or "").strip()
    if not text:
        return ""
    known = {
        "2150": (
            "This document already has an IRN. Use the IRN already stored on it.",
            "इस दस्तावेज़ पर IRN पहले से है। वही IRN उपयोग करें।",
        ),
        "2172": (
            "The buyer GSTIN is not active. Correct the GSTIN before filing.",
            "खरीदार का GSTIN सक्रिय नहीं है। फाइल करने से पहले GSTIN ठीक करें।",
        ),
        "2176": (
            "The HSN on a line is not valid for this invoice date.",
            "किसी पंक्ति का HSN इस चालान की तारीख के लिए मान्य नहीं है।",
        ),
        "3028": (
            "The e-way bill needs a vehicle number and a distance.",
            "ई-वे बिल के लिए वाहन नंबर और दूरी चाहिए।",
        ),
        "404": (
            "The GST portal has no IRN for this document number yet.",
            "इस दस्तावेज़ नंबर का IRN पोर्टल पर अभी नहीं है।",
        ),
    }
    for code, (english, hindi) in known.items():
        if code in text:
            return f"{english} / {hindi}"
    return text[:500]


def verify_irn_result(result: IrnResult) -> None:
    verify_signed_qr_ack(result.irn, result.ack_no, result.einvoice_qr)


def _unwrap_provider_body(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise BusinessRuleError("GSP response is not a JSON object.")
    data = raw.get("Data") or raw.get("data") or raw
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return raw
    return data


def irn_result_from_provider_response(raw: dict) -> IrnResult:
    data = _unwrap_provider_body(raw)
    irn = str(data.get("Irn") or data.get("irn") or "").strip()
    ack_no = str(data.get("AckNo") or data.get("ack_no") or data.get("Ack_No") or "").strip()
    qr = data.get("SignedQRCode") or data.get("signed_qr_code") or data.get("einvoice_qr") or ""
    if not isinstance(qr, str):
        qr = json.dumps(qr) if qr else ""
    qr = qr.strip()
    verify_signed_qr_ack(irn, ack_no, qr)
    ack_raw = data.get("AckDt") or data.get("ack_date") or data.get("AckDate")
    ack_date = parse_provider_datetime(ack_raw) or timezone.now()
    return IrnResult(irn=irn, ack_no=ack_no, ack_date=ack_date, einvoice_qr=qr, raw=raw)


def eway_result_from_provider_response(raw: dict) -> EwayResult:
    data = _unwrap_provider_body(raw)
    bill_no = str(
        data.get("ewayBillNo")
        or data.get("EwbNo")
        or data.get("eway_bill_no")
        or data.get("ewbNo")
        or ""
    ).strip()
    if not bill_no:
        raise BusinessRuleError("e-Way response missing ewayBillNo.")
    valid_upto = parse_eway_valid_upto(raw, allow_default=False)
    return EwayResult(eway_bill_no=bill_no, eway_valid_upto=valid_upto, raw=raw)


def build_gsp_auth_headers(company, creds: dict | None = None) -> dict:
    """NIC / GSP auth header builder per GSP_PROVIDER (cleartax|mastergst|custom)."""
    if creds is None:
        creds = decrypt_gsp_credentials(
            getattr(company, "gsp_credentials_encrypted", "") or ""
        )
    provider = resolve_gsp_provider(company)
    gstin = (
        (getattr(company, "gstin", None) or creds.get("gstin") or "")
    ).strip()
    token = str(creds.get("auth_token") or creds.get("api_key") or "").strip()
    username = str(creds.get("username") or creds.get("user_name") or "").strip()
    client_id = str(creds.get("client_id") or creds.get("clientid") or "").strip()
    client_secret = str(creds.get("client_secret") or creds.get("clientsecret") or "").strip()

    if provider == "cleartax":
        headers = {
            "Authorization": f"Bearer {token}" if token else "",
            "x-cleartax-auth-token": token,
            "gstin": gstin,
        }
        return {k: v for k, v in headers.items() if v}

    if provider == "mastergst":
        headers = {
            "username": username,
            "auth-token": token,
            "client_id": client_id,
            "gstin": gstin,
        }
        return {k: v for k, v in headers.items() if v}

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["AuthToken"] = token
    if username:
        headers["user_name"] = username
        headers["X-GSP-Username"] = username
    if client_id:
        headers["client_id"] = client_id
    if client_secret:
        headers["client_secret"] = client_secret
    if gstin:
        headers["Gstin"] = gstin
    sek = str(creds.get("sek") or creds.get("Sek") or "").strip()
    if sek:
        headers["X-NIC-SEK"] = sek
    return headers


def obtain_gsp_auth_session(company, *, base_url: str, creds: dict | None = None) -> dict:
    """Return auth headers, exchanging username/password for a token when needed."""
    if creds is None:
        creds = decrypt_gsp_credentials(
            getattr(company, "gsp_credentials_encrypted", "") or ""
        )
    if creds.get("auth_token") or creds.get("api_key"):
        return build_gsp_auth_headers(company, creds=creds)
    base = (base_url or "").rstrip("/")
    if not base:
        return build_gsp_auth_headers(company, creds=creds)
    if not (creds.get("username") and (creds.get("password") or creds.get("client_secret"))):
        return build_gsp_auth_headers(company, creds=creds)
    raw = _http_json(
        "POST",
        f"{base}/auth",
        {
            "username": creds.get("username"),
            "password": creds.get("password"),
            "client_id": creds.get("client_id"),
            "client_secret": creds.get("client_secret"),
            "gstin": getattr(company, "gstin", "") or creds.get("gstin") or "",
            "provider": resolve_gsp_provider(company),
        },
    )
    token = str(raw.get("auth_token") or raw.get("AuthToken") or raw.get("token") or "")
    sek = str(raw.get("sek") or raw.get("Sek") or "")
    merged = {**creds, "auth_token": token, "sek": sek}
    return build_gsp_auth_headers(company, creds=merged)


def wrap_irp_payload(payload: dict, *, company=None, creds: dict | None = None) -> dict:
    """Encrypted IRP payload wrapper hook (provider envelope).

    - cleartax: ``{"Data": [payload]}``
    - mastergst: passthrough
    - custom: NIC e-Invoice API 1.04 ``{"Data": "<base64 AES-ECB>"}`` under the
      SEK stored in the encrypted GSP credential blob. No SEK means refuse —
      the old HMAC placeholder is not sent.
    """
    from core.services.nic_irp_crypto import sek_bytes, wrap_nic_invoice_data

    provider = resolve_gsp_provider(company)
    if provider == "cleartax":
        return {"Data": [payload]}
    if provider == "mastergst":
        return payload
    sek = sek_bytes((creds or {}).get("sek") or (creds or {}).get("irp_sek"))
    if sek is None:
        raise BusinessRuleError(
            "Custom IRP provider requires an AES SEK in the encrypted GSP credentials "
            "(key 'sek', base64). Refusing to send an unencrypted or HMAC-placeholder payload."
        )
    return wrap_nic_invoice_data(payload, sek)


def _live_irp_url(base: str, action: str, provider: str) -> str:
    base = base.rstrip("/")
    if provider == "cleartax":
        return f"{base}/v2/eInvoice/{'generate' if action == 'submit' else 'cancel' if action == 'cancel' else 'get'}"
    if provider == "mastergst":
        kind = {"submit": "GENERATE", "cancel": "CANCEL"}.get(action, "GETIRNBYDOC")
        return f"{base}/einvoice/type/{kind}/version/V1_03"
    return f"{base}/irp/invoice" if action == "submit" else f"{base}/irp/cancel" if action == "cancel" else f"{base}/irp/invoice"


def _live_eway_url(base: str, action: str, provider: str) -> str:
    base = base.rstrip("/")
    if provider == "cleartax":
        return f"{base}/v1/ewaybill/{'generate' if action == 'submit' else 'cancel'}"
    if provider == "mastergst":
        path = "genewaybill" if action == "submit" else "canewb"
        return f"{base}/ewaybillapi/v1.03/ewayapi/{path}"
    return f"{base}/eway/generate" if action == "submit" else f"{base}/eway/cancel"


class SandboxIrpAdapter:
    def lookup_by_doc(self, doc_no: str) -> IrnResult | None:
        """Sandbox has no partner to query. Live adapters override this."""
        return None

    def submit(self, payload: dict) -> IrnResult:
        blob = json.dumps(payload, sort_keys=True, default=str).encode()
        digest = hashlib.sha256(blob).hexdigest()
        irn = digest
        ack_no = digest[:16].upper()
        qr = json.dumps({"irn": irn, "ack": ack_no, "sandbox": True})
        return IrnResult(
            irn=irn,
            ack_no=ack_no,
            ack_date=timezone.now(),
            einvoice_qr=qr,
            raw={"provider": "sandbox", "irn": irn},
        )

    def cancel(self, irn: str, cnl_rsn: str = "1", cnl_rem: str = "Cancelled") -> dict:
        return {"provider": "sandbox", "cancelled": True, "irn": irn, "CnlRsn": cnl_rsn, "CnlRem": cnl_rem}


class SandboxEwayAdapter:
    def submit(self, payload: dict) -> EwayResult:
        blob = json.dumps(payload, sort_keys=True, default=str).encode()
        digest = hashlib.sha256(blob).hexdigest()
        bill_no = digest[:12].upper()
        # Hash sandbox has no provider validity — documented +1 day default only.
        return EwayResult(
            eway_bill_no=bill_no,
            eway_valid_upto=parse_eway_valid_upto(
                {"provider": "sandbox", "eway_bill_no": bill_no},
                allow_default=True,
            ),
            raw={"provider": "sandbox", "eway_bill_no": bill_no},
        )

    def cancel(self, eway_bill_no: str) -> dict:
        return {"provider": "sandbox", "cancelled": True, "eway_bill_no": eway_bill_no}

    def update_vehicle(self, payload: dict) -> dict:
        return {"provider": "sandbox", "updated": True, **payload}

    def extend_validity(self, payload: dict) -> dict:
        return {"provider": "sandbox", "extended": True, **payload}


def _json_object(raw) -> dict:
    """Live GSTR `|` merge requires a mapping; GSP bodies are not always objects."""
    return raw if isinstance(raw, dict) else {"raw": raw}


def assert_safe_outbound_url(url: str) -> None:
    """B7-015: an operator-set base URL must be http(s), and https outside dev.

    Blocks `file://`, `ftp://`, gopher, etc. and obvious link-local / loopback
    metadata hosts so a misconfigured (or tampered) GSP/GSTIN base URL cannot be
    turned into a local file read or a 169.254.169.254 fetch.
    """
    from urllib.parse import urlsplit

    parts = urlsplit(url or "")
    scheme = (parts.scheme or "").lower()
    allowed = {"http", "https"}
    if getattr(settings, "DJANGO_ENV", "") in ("production", "staging"):
        allowed = {"https"}
    if scheme not in allowed:
        raise BusinessRuleError(
            f"Refusing outbound request to a {scheme or 'schemeless'} URL."
        )
    host = (parts.hostname or "").lower()
    if host in ("169.254.169.254", "metadata", "metadata.google.internal"):
        raise BusinessRuleError("Refusing outbound request to a metadata host.")


def _http_json(method: str, url: str, payload: dict | None, headers: dict | None = None) -> dict:
    assert_safe_outbound_url(url)
    data = None if payload is None else json.dumps(payload, default=str).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    from core.circuit_breaker import CircuitOpenError, call as circuit_call

    def _do():
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode() or "{}"
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            raise BusinessRuleError(f"GSP HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise BusinessRuleError(f"GSP unreachable: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise BusinessRuleError("GSP response is not valid JSON.") from exc

    try:
        return circuit_call("gsp_einvoice", _do, failure_threshold=5, cooldown_seconds=30)
    except CircuitOpenError as exc:
        raise BusinessRuleError("GSP is temporarily unavailable. Try again shortly.") from exc


class HttpSandboxIrpAdapter:
    """POST to provider sandbox base URL; falls back to hash if URL unset."""

    def __init__(self, company):
        self.company = company
        self.base = (getattr(settings, "GSP_SANDBOX_BASE_URL", "") or "").rstrip("/")

    def submit(self, payload: dict) -> IrnResult:
        if not self.base:
            logger.info("GSP_SANDBOX_BASE_URL unset — using hash sandbox IRP")
            return SandboxIrpAdapter().submit(payload)
        raw = _http_json("POST", f"{self.base}/irp/invoice", payload)
        return irn_result_from_provider_response(raw)

    def cancel(self, irn: str, cnl_rsn: str = "1", cnl_rem: str = "Cancelled") -> dict:
        if not self.base:
            return SandboxIrpAdapter().cancel(irn, cnl_rsn=cnl_rsn, cnl_rem=cnl_rem)
        return _http_json(
            "POST",
            f"{self.base}/irp/cancel",
            {"irn": irn, "CnlRsn": cnl_rsn, "CnlRem": cnl_rem},
        )

    def lookup_by_doc(self, doc_no: str) -> IrnResult | None:
        if not self.base or not (doc_no or "").strip():
            return None
        try:
            raw = _http_json("GET", f"{self.base}/irp/invoice?doc_no={doc_no}", None)
        except BusinessRuleError as exc:
            if "404" in str(exc):
                return None
            raise
        if not isinstance(raw, dict) or not (raw.get("Irn") or raw.get("irn")):
            return None
        return irn_result_from_provider_response(raw)


class HttpSandboxEwayAdapter:
    def __init__(self, company):
        self.company = company
        self.base = (getattr(settings, "GSP_SANDBOX_BASE_URL", "") or "").rstrip("/")

    def submit(self, payload: dict) -> EwayResult:
        if not self.base:
            logger.info("GSP_SANDBOX_BASE_URL unset — using hash sandbox e-Way")
            return SandboxEwayAdapter().submit(payload)
        raw = _http_json("POST", f"{self.base}/eway/generate", payload)
        return eway_result_from_provider_response(raw)

    def cancel(self, eway_bill_no: str) -> dict:
        if not self.base:
            return SandboxEwayAdapter().cancel(eway_bill_no)
        return _http_json("POST", f"{self.base}/eway/cancel", {"eway_bill_no": eway_bill_no})


class LiveIrpAdapter:
    """Certified live GSP/IRP HTTP adapter (BB-000624).

    Final Gate: production (and staging) live submit is allowed only when
    ``GSP_LIVE_ENABLED=1`` AND ``GSP_CERTIFIED=1`` AND ``DJANGO_ENV`` is
    production or staging. Uncertified live stays fail-closed. This adapter is
    protocol-shaped (provider auth session, IRP wrap hook, SignedQRCode + AckNo
    verification) — not a fake-success stub. Operator sign-off of
    ``GSP_CERTIFIED`` is the Final Gate before any 10/10 live-NIC claim.
    """

    def __init__(self, company):
        self.company = company
        if not _live_enabled() or not _gsp_certified():
            raise BusinessRuleError(
                "Live IRP adapter requires GSP_LIVE_ENABLED=1 and GSP_CERTIFIED=1. "
                "Disable GSP_LIVE_ENABLED in production until a certified GSP ships."
            )
        # Custom is allowed only when the credential blob already holds a SEK.
        # GSP_LIVE_ENABLED and GSP_CERTIFIED are still required above. A missing
        # SEK is a hard stop — there is no HMAC fallback.
        if resolve_gsp_provider(company) == "custom":
            from core.services.nic_irp_crypto import sek_bytes

            creds = {}
            try:
                creds = decrypt_gsp_credentials(
                    getattr(company, "gsp_credentials_encrypted", "") or ""
                )
            except Exception:
                creds = {}
            if sek_bytes((creds or {}).get("sek") or (creds or {}).get("irp_sek")) is None:
                raise BusinessRuleError(
                    "Live IRP adapter refuses provider='custom' without an AES SEK in "
                    "the encrypted GSP credentials. NIC e-Invoice API 1.04 wrapping is "
                    "implemented; it does not run until that key is present."
                )

    def _base(self) -> str:
        return (getattr(settings, "GSP_LIVE_BASE_URL", None) or "").rstrip("/")

    def _creds(self) -> dict:
        creds = decrypt_gsp_credentials(
            getattr(self.company, "gsp_credentials_encrypted", "") or ""
        )
        reject_placeholder_gsp_credentials(creds)
        return creds

    def _headers(self) -> dict:
        creds = self._creds()
        base = self._base()
        if not creds or not base:
            raise BusinessRuleError(
                "Live GSP is not configured. Set company GSP secrets + GSP_LIVE_BASE_URL."
            )
        return obtain_gsp_auth_session(self.company, base_url=base, creds=creds)

    def submit(self, payload: dict) -> IrnResult:
        base = self._base()
        headers = self._headers()
        provider = resolve_gsp_provider(self.company)
        wrapped = wrap_irp_payload(payload, company=self.company, creds=self._creds())
        raw = _http_json("POST", _live_irp_url(base, "submit", provider), wrapped, headers=headers)
        return irn_result_from_provider_response(raw)

    def cancel(self, irn: str, cnl_rsn: str = "1", cnl_rem: str = "Cancelled") -> dict:
        base = self._base()
        headers = self._headers()
        provider = resolve_gsp_provider(self.company)
        return _http_json(
            "POST",
            _live_irp_url(base, "cancel", provider),
            {"irn": irn, "CnlRsn": cnl_rsn, "CnlRem": cnl_rem},
            headers=headers,
        )

    def lookup_by_doc(self, doc_no: str) -> IrnResult | None:
        doc_no = (doc_no or "").strip()
        if not doc_no:
            return None
        base = self._base()
        headers = self._headers()
        provider = resolve_gsp_provider(self.company)
        url = _live_irp_url(base, "lookup", provider)
        try:
            raw = _http_json("GET", f"{url}?doc_no={doc_no}", None, headers=headers)
        except BusinessRuleError as exc:
            if "404" in str(exc):
                return None
            raise
        if not isinstance(raw, dict) or not (raw.get("Irn") or raw.get("irn")):
            return None
        return irn_result_from_provider_response(raw)


class LiveEwayAdapter:
    """Certified live e-Way HTTP adapter (BB-000624). Same Final Gate as LiveIrpAdapter."""

    def __init__(self, company):
        self.company = company
        if not _live_enabled() or not _gsp_certified():
            raise BusinessRuleError(
                "Live e-Way adapter requires GSP_LIVE_ENABLED=1 and GSP_CERTIFIED=1. "
                "Disable GSP_LIVE_ENABLED in production until a certified GSP ships."
            )

    def _base(self) -> str:
        return (getattr(settings, "GSP_LIVE_BASE_URL", None) or "").rstrip("/")

    def _creds(self) -> dict:
        creds = decrypt_gsp_credentials(
            getattr(self.company, "gsp_credentials_encrypted", "") or ""
        )
        reject_placeholder_gsp_credentials(creds)
        return creds

    def _headers(self) -> dict:
        creds = self._creds()
        base = self._base()
        if not creds or not base:
            raise BusinessRuleError(
                "Live e-Way GSP is not configured. Set company GSP secrets + GSP_LIVE_BASE_URL."
            )
        return obtain_gsp_auth_session(self.company, base_url=base, creds=creds)

    def submit(self, payload: dict) -> EwayResult:
        base = self._base()
        headers = self._headers()
        provider = resolve_gsp_provider(self.company)
        raw = _http_json(
            "POST", _live_eway_url(base, "submit", provider), payload, headers=headers
        )
        return eway_result_from_provider_response(raw)

    def cancel(self, eway_bill_no: str) -> dict:
        base = self._base()
        headers = self._headers()
        provider = resolve_gsp_provider(self.company)
        return _http_json(
            "POST",
            _live_eway_url(base, "cancel", provider),
            {"eway_bill_no": eway_bill_no},
            headers=headers,
        )


class StubGstrFilingAdapter:
    """Offline / not-live filing — raises until live credentials enable HTTP."""

    def upload_gstr1(self, payload: dict) -> dict:
        raise BusinessRuleError(
            "GSTR filing upload requires live GSP credentials (Final Gate)."
        )

    def upload_gstr3b(self, payload: dict) -> dict:
        raise BusinessRuleError(
            "GSTR-3B filing upload requires live GSP credentials (Final Gate)."
        )

    def fetch_gstr2b(self, period: str) -> dict:
        raise BusinessRuleError(
            "GSTR-2B fetch requires live GSP credentials; use file ingest meanwhile."
        )


class HttpSandboxGstrAdapter:
    """Cassette-friendly sandbox GSTR upload/fetch via urllib ``_http_json``."""

    def __init__(self, company):
        self.company = company
        self.base = (getattr(settings, "GSP_SANDBOX_BASE_URL", "") or "").rstrip("/")

    def upload_gstr1(self, payload: dict) -> dict:
        if not self.base:
            raise BusinessRuleError("GSP_SANDBOX_BASE_URL required for GSTR-1 sandbox upload.")
        return _json_object(_http_json("POST", f"{self.base}/gstr1/upload", payload))

    def upload_gstr3b(self, payload: dict) -> dict:
        if not self.base:
            raise BusinessRuleError("GSP_SANDBOX_BASE_URL required for GSTR-3B sandbox upload.")
        return _json_object(_http_json("POST", f"{self.base}/gstr3b/upload", payload))

    def fetch_gstr2b(self, period: str) -> dict:
        if not self.base:
            raise BusinessRuleError("GSP_SANDBOX_BASE_URL required for GSTR-2B sandbox fetch.")
        return _http_json("POST", f"{self.base}/gstr2b/fetch", {"period": period})


class LiveGstrFilingAdapter:
    """Fail-closed live GSTR-1/3B upload. Same gate as LiveIrpAdapter."""

    def __init__(self, company):
        self.company = company
        if not _live_enabled() or not _gsp_certified():
            raise BusinessRuleError(
                "Live GSTR adapter requires GSP_LIVE_ENABLED=1 and GSP_CERTIFIED=1. "
                "Disable GSP_LIVE_ENABLED until a certified GSP ships."
            )

    def _base(self) -> str:
        return (getattr(settings, "GSP_LIVE_BASE_URL", None) or "").rstrip("/")

    def _creds(self) -> dict:
        creds = decrypt_gsp_credentials(
            getattr(self.company, "gsp_credentials_encrypted", "") or ""
        )
        reject_placeholder_gsp_credentials(creds)
        return creds

    def _headers(self) -> dict:
        creds = self._creds()
        base = self._base()
        if not creds or not base:
            raise BusinessRuleError(
                "Live GSTR GSP is not configured. Set company GSP secrets + GSP_LIVE_BASE_URL."
            )
        return obtain_gsp_auth_session(self.company, base_url=base, creds=creds)

    def upload_gstr1(self, payload: dict) -> dict:
        base = self._base()
        headers = self._headers()
        provider = resolve_gsp_provider(self.company)
        return _json_object(_http_json("POST", f"{base}/gstr1/upload", payload, headers=headers)) | {
            "provider": provider,
        }

    def upload_gstr3b(self, payload: dict) -> dict:
        base = self._base()
        headers = self._headers()
        provider = resolve_gsp_provider(self.company)
        return _json_object(_http_json("POST", f"{base}/gstr3b/upload", payload, headers=headers)) | {
            "provider": provider,
        }

    def fetch_gstr2b(self, period: str) -> dict:
        base = self._base()
        headers = self._headers()
        return _http_json("POST", f"{base}/gstr2b/fetch", {"period": period}, headers=headers)


HttpSandboxGstrFilingAdapter = HttpSandboxGstrAdapter


def get_irp_adapter(company) -> IrpAdapter:
    env = _django_env()
    provider = (getattr(company, "gsp_provider", None) or "").strip().lower()
    want_live = _live_enabled() and provider not in ("", "sandbox")
    if want_live:
        if env in ("production", "staging") and not _gsp_certified():
            raise BusinessRuleError(
                "Live IRP is fail-closed in production until NIC/GSP protocol is implemented."
            )
        return LiveIrpAdapter(company)
    if _http_sandbox_enabled():
        return HttpSandboxIrpAdapter(company)
    return SandboxIrpAdapter()


def get_eway_adapter(company) -> EwayAdapter:
    env = _django_env()
    provider = (getattr(company, "gsp_provider", None) or "").strip().lower()
    want_live = _live_enabled() and provider not in ("", "sandbox")
    if env in ("production", "staging") and not _gsp_certified():
        raise BusinessRuleError(
            "e-Way GSP is not available in production/staging until live "
            "GSP HTTP is configured."
        )
    if want_live:
        return LiveEwayAdapter(company)
    if _http_sandbox_enabled():
        return HttpSandboxEwayAdapter(company)
    return SandboxEwayAdapter()


def get_gstr_filing_adapter(company) -> GstrFilingAdapter:
    env = _django_env()
    provider = (getattr(company, "gsp_provider", None) or "").strip().lower()
    want_live = _live_enabled() and provider not in ("", "sandbox")
    if want_live:
        if env in ("production", "staging") and not _gsp_certified():
            raise BusinessRuleError(
                "Live GSTR upload is fail-closed until GSP_CERTIFIED=1 and named-provider secrets."
            )
        return LiveGstrFilingAdapter(company)
    if _http_sandbox_enabled():
        return HttpSandboxGstrAdapter(company)
    return StubGstrFilingAdapter()
