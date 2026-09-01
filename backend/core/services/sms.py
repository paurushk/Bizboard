"""SMS provider abstraction — console stub + MSG91/Twilio HTTP adapters (Wave 16A).

Providers:
- ``console`` / ``stub`` / unset: logs only in development/test; blocked in prod/staging.
- ``msg91``: requires MSG91_AUTH_KEY (+ optional MSG91_TEMPLATE_ID, MSG91_SENDER).
- ``twilio``: requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.

Fail closed when credentials missing. Live vendor DLT / templates remain ops Final Gate.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from core.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)

_STUB_PROVIDERS = frozenset({"", "console", "stub"})
_HTTP_PROVIDERS = frozenset({"msg91", "twilio"})


def _env() -> str:
    return (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()


def _looks_indian_mobile(phone: str) -> bool:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("91") and len(digits) >= 12:
        return True
    if len(digits) == 10:
        return True
    return (phone or "").strip().startswith("+91")


def _send_msg91(phone: str, code: str) -> None:
    auth = (getattr(settings, "MSG91_AUTH_KEY", "") or "").strip()
    if not auth:
        raise BusinessRuleError("MSG91_AUTH_KEY is required when SMS_PROVIDER=msg91.")
    template = (getattr(settings, "MSG91_TEMPLATE_ID", "") or "").strip()
    sender = (getattr(settings, "MSG91_SENDER", "") or "BIZBRD").strip()
    # SEC-04: DLT template required for Indian numbers outside local/dev.
    env = _env()
    prod_like = env in ("production", "staging") or not bool(getattr(settings, "DEBUG", True))
    if not template:
        if prod_like and _looks_indian_mobile(phone):
            raise BusinessRuleError(
                "MSG91_TEMPLATE_ID is required for Indian numbers when SMS_PROVIDER=msg91 "
                "in production/staging (or DEBUG=0)."
            )
        logger.warning(
            "MSG91_TEMPLATE_ID is unset — OTP may fail for DLT-registered Indian routes."
        )
    # MSG91 flow API — template OTP; body adapted for unit tests via mock.
    payload = urllib.parse.urlencode(
        {
            "authkey": auth,
            "mobile": phone,
            "otp": code,
            "sender": sender,
            **({"template_id": template} if template else {}),
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.msg91.com/api/v5/otp",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                raise BusinessRuleError(f"MSG91 OTP send failed with HTTP {resp.status}.")
            import json

            try:
                payload_json = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                payload_json = {}
            if isinstance(payload_json, dict) and str(payload_json.get("type") or "").lower() == "error":
                msg = payload_json.get("message") or payload_json.get("msg") or raw_body[:200]
                raise BusinessRuleError(f"MSG91 OTP send failed: {msg}")
    except urllib.error.HTTPError as exc:
        raise BusinessRuleError(f"MSG91 OTP send failed: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BusinessRuleError(f"MSG91 OTP unreachable: {exc.reason}") from exc


def _send_twilio(phone: str, code: str) -> None:
    sid = (getattr(settings, "TWILIO_ACCOUNT_SID", "") or "").strip()
    token = (getattr(settings, "TWILIO_AUTH_TOKEN", "") or "").strip()
    from_num = (getattr(settings, "TWILIO_FROM_NUMBER", "") or "").strip()
    if not sid or not token or not from_num:
        raise BusinessRuleError(
            "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER are required "
            "when SMS_PROVIDER=twilio."
        )
    body = f"Your BizBoard OTP is {code}"
    data = urllib.parse.urlencode({"To": phone, "From": from_num, "Body": body}).encode()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    req = urllib.request.Request(url, data=data, method="POST")
    import base64

    basic = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req.add_header("Authorization", f"Basic {basic}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                raise BusinessRuleError(f"Twilio OTP send failed with HTTP {resp.status}.")
    except urllib.error.HTTPError as exc:
        raise BusinessRuleError(f"Twilio OTP send failed: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BusinessRuleError(f"Twilio OTP unreachable: {exc.reason}") from exc


def _send_twilio_text(phone: str, body: str) -> None:
    sid = (getattr(settings, "TWILIO_ACCOUNT_SID", "") or "").strip()
    token = (getattr(settings, "TWILIO_AUTH_TOKEN", "") or "").strip()
    from_num = (getattr(settings, "TWILIO_FROM_NUMBER", "") or "").strip()
    if not sid or not token or not from_num:
        raise BusinessRuleError(
            "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER are required "
            "when SMS_PROVIDER=twilio."
        )
    data = urllib.parse.urlencode(
        {"To": phone, "From": from_num, "Body": (body or "BizBoard")[:1600]}
    ).encode()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    req = urllib.request.Request(url, data=data, method="POST")
    import base64

    basic = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req.add_header("Authorization", f"Basic {basic}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                raise BusinessRuleError(f"Twilio SMS send failed with HTTP {resp.status}.")
    except urllib.error.HTTPError as exc:
        raise BusinessRuleError(f"Twilio SMS send failed: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BusinessRuleError(f"Twilio SMS unreachable: {exc.reason}") from exc


class SmsProvider:
    @staticmethod
    def send_otp(phone: str, code: str) -> None:
        provider = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        env = _env()

        if provider in _STUB_PROVIDERS:
            if env not in ("development", "test", ""):
                raise BusinessRuleError(
                    "SMS stub providers cannot send OTP outside development/test. "
                    "Configure SMS_PROVIDER=msg91 or twilio with credentials."
                )
            if settings.OTP_DEBUG_ECHO:
                logger.debug(
                    "OTP debug echo code=%s for phone ending %s",
                    code,
                    phone[-4:] if len(phone) >= 4 else "****",
                )
            return

        if provider == "msg91":
            _send_msg91(phone, code)
            return
        if provider == "twilio":
            _send_twilio(phone, code)
            return

        raise BusinessRuleError(
            f"SMS provider '{provider}' is not implemented. "
            "Use console (dev), msg91, or twilio."
        )

    @staticmethod
    def send_text(phone: str, body: str) -> None:
        """A-07 dunning SMS. Stub in test/dev; Twilio/MSG91 when configured."""
        provider = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        env = _env()
        if provider in _STUB_PROVIDERS:
            if env not in ("development", "test", ""):
                raise BusinessRuleError(
                    "SMS stub providers cannot send outside development/test."
                )
            logger.info("SMS stub to %s: %s", phone[-4:] if len(phone) >= 4 else "****", (body or "")[:80])
            return
        if provider == "twilio":
            _send_twilio_text(phone, body)
            return
        if provider == "msg91":
            # OTP API is not a dunning channel; fail closed unless a stub env.
            raise BusinessRuleError("MSG91 OTP API cannot send AR dunning texts. Use twilio or console.")
        raise BusinessRuleError(
            f"SMS provider '{provider}' is not implemented for text messages."
        )
