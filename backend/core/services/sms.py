"""SMS provider abstraction — console stub + MSG91/Twilio HTTP adapters (Wave 16A).

Providers:
- ``console`` / ``stub`` / unset: logs only in development/test; blocked in prod/staging.
- ``msg91``: requires MSG91_AUTH_KEY (+ optional MSG91_TEMPLATE_ID, MSG91_SENDER).
- ``twilio``: requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.

Fail closed when credentials missing. Every SMS is a registered template
(``core/message_templates.py``, WP-CM2) and passes the caps in ``sms_guard`` (WP-AB1) first.
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

            if not (raw_body or "").strip():
                raise BusinessRuleError("MSG91 OTP send failed: empty response.")
            try:
                payload_json = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                raise BusinessRuleError("MSG91 OTP send failed: invalid response.") from exc
            if not isinstance(payload_json, dict):
                raise BusinessRuleError("MSG91 OTP send failed: invalid response.")
            if str(payload_json.get("type") or "").lower() == "error":
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


def _guarded(phone: str, purpose: str, send) -> None:
    """WP-AB1: count the attempt before the provider is called; it stays counted if the send fails."""
    from core.services import sms_guard

    sms_guard.check_and_count(phone, purpose)
    try:
        send()
    except Exception:
        sms_guard.record_result(purpose, ok=False)
        raise
    sms_guard.record_result(purpose, ok=True)


def _send_msg91_flow(phone: str, template_id: str, values: dict) -> None:
    """WP-CM2: a non-OTP SMS through MSG91's flow API, which sends the DLT template by ID."""
    import json

    auth = (getattr(settings, "MSG91_AUTH_KEY", "") or "").strip()
    if not auth:
        raise BusinessRuleError("MSG91_AUTH_KEY is required when SMS_PROVIDER=msg91.")
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    body = json.dumps(
        {"template_id": template_id, "short_url": "0", "recipients": [{"mobiles": digits, **values}]}
    ).encode()
    req = urllib.request.Request(
        "https://control.msg91.com/api/v5/flow/",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "authkey": auth},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                raise BusinessRuleError(f"MSG91 SMS send failed with HTTP {resp.status}.")
            try:
                payload = json.loads(raw or "{}")
            except json.JSONDecodeError as exc:
                raise BusinessRuleError("MSG91 SMS send failed: invalid response.") from exc
            if isinstance(payload, dict) and str(payload.get("type") or "").lower() == "error":
                raise BusinessRuleError(f"MSG91 SMS send failed: {payload.get('message') or raw[:200]}")
    except urllib.error.HTTPError as exc:
        raise BusinessRuleError(f"MSG91 SMS send failed: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BusinessRuleError(f"MSG91 SMS unreachable: {exc.reason}") from exc


class SmsProvider:
    @staticmethod
    def send_otp(phone: str, code: str) -> None:
        SmsProvider.send_template(phone, "otp", code=code)

    @staticmethod
    def send_template(phone: str, key: str, **values) -> None:
        """WP-CM2: the only way to send an SMS. ``key`` is in ``core.message_templates.SMS_TEMPLATES``."""
        from accounts.otp_utils import normalize_e164
        from core.message_templates import sms_template

        tpl = sms_template(key)
        text = tpl.render(**values)
        # One canonical number for the guard, the DLT check and the provider (a stored "09876…" or
        # "+91 098…" would otherwise be counted one way and sent another).
        try:
            phone = normalize_e164(phone)
        except ValueError:
            raise BusinessRuleError("That is not a valid mobile number.", code="SMS_BAD_NUMBER") from None
        prod_like = _env() in ("production", "staging") or not bool(getattr(settings, "DEBUG", True))
        provider = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        # MSG91 sends by DLT template ID; Twilio carries its own DLT registration on the sender.
        if (
            prod_like
            and provider == "msg91"
            and _looks_indian_mobile(phone)
            and not tpl.dlt_template_id()
        ):
            raise BusinessRuleError(
                f"SMS template '{key}' has no DLT template ID ({tpl.dlt_setting}); Indian operators would drop it."
            )

        def send():
            if key == "otp":
                SmsProvider._send_otp(phone, values["code"])
            elif provider == "msg91":
                _send_msg91_flow(phone, tpl.dlt_template_id(), {k: str(values[k]) for k in tpl.variables})
            else:
                SmsProvider._send_text(phone, text)

        _guarded(phone, key, send)

    @staticmethod
    def _send_otp(phone: str, code: str) -> None:
        provider = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        env = _env()

        if provider in _STUB_PROVIDERS:
            if env not in ("development", "test", ""):
                raise BusinessRuleError(
                    "SMS stub providers cannot send OTP outside development/test. "
                    "Configure SMS_PROVIDER=msg91 or twilio with credentials."
                )
            if settings.OTP_DEBUG_ECHO:
                # B7-012: this DOES log the plaintext code — that is the whole
                # point of OTP_DEBUG_ECHO (dev/CI login without SMS). It is
                # hard-rejected in production/staging (see settings). The
                # settings comment claiming "never the code" was wrong and has
                # been corrected.
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
    def _send_text(phone: str, body: str) -> None:
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
        raise BusinessRuleError(
            f"SMS provider '{provider}' is not implemented for text messages."
        )
