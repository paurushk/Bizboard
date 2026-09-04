"""Payment gateway adapter Protocol + Razorpay / sandbox (Phase 3.1).

Cashfree/PayU support create-link, webhook verify/parse, and refund HTTP calls
when credentials are configured. Named providers never fall back to SandboxAdapter
when credentials are empty.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from core.exceptions import BusinessRuleError
from core.services.gsp_secrets import decrypt_gsp_credentials, encrypt_gsp_credentials

# Sandbox is only allowed in these DJANGO_ENV values (unset/unknown ⇒ production-safe).
_SANDBOX_ALLOWED_ENVS = frozenset({"development", "test", "local"})


def _json_body(body: bytes) -> dict:
    """PAY-06: a provider shipping a new / malformed payload shape must yield a
    clean 400 ("Unrecognized payload"), not an uncaught 500 in the webhook view.
    """
    try:
        data = json.loads((body or b"").decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _stable_refund_key(provider_payment_id: str, amount: Decimal) -> str:
    """PAY-09: never issue a non-idempotent refund. Callers normally pass an
    explicit key (``refund_idempotency_key(gp.id, amount)``); if one is omitted
    fall back to a deterministic key so a retried refund cannot double-pay.
    """
    amt = str(Decimal(str(amount or 0)).quantize(Decimal("0.01")))
    return "bb_rf_" + hashlib.sha256(f"{provider_payment_id}|{amt}".encode()).hexdigest()[:32]


def _payu_body(body: bytes) -> dict:
    """PAY-03: PayU's S2S / webhook callback is posted as
    ``application/x-www-form-urlencoded`` (``key=..&txnid=..&status=..&hash=..``),
    NOT JSON. Parse form-encoded first, fall back to JSON for hand-crafted
    payloads / tests. Repeated keys collapse to the last value.
    """
    from urllib.parse import parse_qsl

    raw = (body or b"").decode("utf-8", "replace").strip()
    if not raw:
        return {}
    if raw[0] in "{[":
        return _json_body(body)
    pairs = parse_qsl(raw, keep_blank_values=True)
    if not pairs:
        return _json_body(body)
    return {k: v for k, v in pairs}


def get_disabled_providers() -> frozenset[str]:
    """Cashfree/PayU disabled unless ENABLE_* settings/env are true."""
    from django.conf import settings

    disabled: set[str] = set()
    if not getattr(settings, "ENABLE_CASHFREE", False):
        disabled.add("cashfree")
    if not getattr(settings, "ENABLE_PAYU", False):
        disabled.add("payu")
    return frozenset(disabled)


class _DisabledProvidersView:
    """Lazy container so `provider in DISABLED_PROVIDERS` reads live settings."""

    def __contains__(self, item) -> bool:
        return item in get_disabled_providers()

    def __iter__(self):
        return iter(get_disabled_providers())

    def __len__(self) -> int:
        return len(get_disabled_providers())

    def __bool__(self) -> bool:
        return bool(get_disabled_providers())


DISABLED_PROVIDERS = _DisabledProvidersView()


def encrypt_gateway_credentials(payload: dict[str, Any] | None) -> str:
    return encrypt_gsp_credentials(payload)


def decrypt_gateway_credentials(ciphertext: str) -> dict[str, Any]:
    return decrypt_gsp_credentials(ciphertext)


@dataclass
class CreateLinkResult:
    provider_link_id: str
    short_url: str
    raw: dict[str, Any]


@dataclass
class WebhookEvent:
    provider_payment_id: str
    amount: Decimal
    fee: Decimal
    status: str  # CAPTURED | FAILED | REFUNDED
    payment_link_id: str
    raw: dict[str, Any]


class PaymentGatewayAdapter(Protocol):
    name: str

    def create_payment_link(
        self,
        *,
        amount: Decimal,
        description: str,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        reference: str,
        callback_url: str,
        expire_by: int | None = None,
    ) -> CreateLinkResult: ...

    def verify_webhook(self, *, headers: dict[str, str], body: bytes) -> bool: ...

    def parse_webhook(self, *, body: bytes) -> WebhookEvent | None: ...

    def refund(self, *, provider_payment_id: str, amount: Decimal, idempotency_key: str = "") -> dict[str, Any]: ...


def _sandbox_webhook_secret_base() -> str:
    """BB-000258: base HMAC secret for sandbox webhooks (required outside DJANGO_ENV=test)."""
    from django.conf import settings

    secret = (getattr(settings, "SANDBOX_WEBHOOK_SECRET", None) or "").strip()
    django_env = (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()
    if secret:
        return secret
    if django_env == "test" or getattr(settings, "TESTING", False):
        return "test-sandbox-webhook-secret"
    raise BusinessRuleError(
        "SANDBOX_WEBHOOK_SECRET is required for sandbox payment webhooks outside tests."
    )


def sandbox_webhook_secret_for_company(company_id) -> str:
    """BB-000412: per-company derived secret — global base alone cannot forge other tenants."""
    base = _sandbox_webhook_secret_base()
    return hmac.new(
        base.encode(),
        f"bizboard:sandbox:company:{company_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _sandbox_webhook_secret() -> str:
    """Backward-compatible alias (tests / probes without company). Prefer company-bound secret."""
    return _sandbox_webhook_secret_base()


class SandboxAdapter:
    """Deterministic fake gateway for CI / local when provider=sandbox explicitly."""

    name = "sandbox"

    def __init__(self, company_id=None):
        self.company_id = company_id

    def create_payment_link(
        self,
        *,
        amount: Decimal,
        description: str,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        reference: str,
        callback_url: str,
        expire_by: int | None = None,
        **kwargs,
    ) -> CreateLinkResult:
        link_id = f"plink_sandbox_{secrets.token_hex(8)}"
        return CreateLinkResult(
            provider_link_id=link_id,
            short_url=f"{callback_url.rstrip('/')}/sandbox/{link_id}",
            raw={"amount": str(amount), "reference": reference, "description": description},
        )

    def verify_webhook(self, *, headers: dict[str, str], body: bytes) -> bool:
        # BB-000258: HMAC-SHA256 over body — never accept static "ok".
        # BB-000412: bind secret to company when known.
        sig = headers.get("X-Sandbox-Signature") or headers.get("x-sandbox-signature") or ""
        if not sig:
            return False
        try:
            if self.company_id is not None:
                secret = sandbox_webhook_secret_for_company(self.company_id)
            else:
                secret = _sandbox_webhook_secret_base()
        except BusinessRuleError:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)

    def parse_webhook(self, *, body: bytes) -> WebhookEvent | None:
        data = _json_body(body)
        if not data:
            return None
        return WebhookEvent(
            provider_payment_id=str(data.get("payment_id") or data.get("id") or ""),
            amount=Decimal(str(data.get("amount", "0"))),
            fee=Decimal(str(data.get("fee", "0"))),
            status=str(data.get("status", "CAPTURED")).upper(),
            payment_link_id=str(data.get("payment_link_id") or ""),
            raw=data,
        )

    def refund(self, *, provider_payment_id: str, amount: Decimal, idempotency_key: str = "") -> dict[str, Any]:
        idempotency_key = idempotency_key or _stable_refund_key(provider_payment_id, amount)
        return {"id": f"rfnd_sandbox_{secrets.token_hex(6)}", "payment_id": provider_payment_id, "amount": str(amount)}

    def cancel_payment_link(self, *, provider_link_id: str) -> None:
        return


class RazorpayAdapter:
    name = "razorpay"

    def __init__(self, credentials: dict[str, Any]):
        self.key_id = credentials.get("key_id") or credentials.get("api_key") or ""
        self.key_secret = credentials.get("key_secret") or credentials.get("api_secret") or ""
        # BB-000307: dedicated webhook_secret required — no key_secret fallback.
        self.webhook_secret = (credentials.get("webhook_secret") or "").strip()

    def create_payment_link(self, **kwargs) -> CreateLinkResult:
        if not self.key_id or not self.key_secret:
            raise BusinessRuleError("Razorpay credentials are not configured.")

        amount = kwargs["amount"]
        amount_paise = int(Decimal(amount).quantize(Decimal("0.01")) * 100)
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": bool(
                kwargs.get("accept_partial", kwargs.get("allow_partial", False))
            ),
            "description": kwargs.get("description") or "Payment",
            "customer": {
                "name": kwargs.get("customer_name") or "",
                "email": kwargs.get("customer_email") or "",
                "contact": kwargs.get("customer_phone") or "",
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {"reference": kwargs.get("reference") or ""},
            "callback_url": kwargs.get("callback_url") or "",
            "callback_method": "get",
        }
        if kwargs.get("expire_by"):
            payload["expire_by"] = int(kwargs["expire_by"])

        import base64

        import requests

        auth = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode()).decode()
        resp = requests.post(
            "https://api.razorpay.com/v1/payment_links",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise BusinessRuleError(
                f"Razorpay payment link failed (HTTP {resp.status_code}). Check credentials and retry."
            )
        data = resp.json()
        return CreateLinkResult(
            provider_link_id=str(data.get("id") or ""),
            short_url=str(data.get("short_url") or data.get("url") or ""),
            raw=data,
        )

    def verify_webhook(self, *, headers: dict[str, str], body: bytes) -> bool:
        sig = headers.get("X-Razorpay-Signature") or headers.get("x-razorpay-signature") or ""
        if not self.webhook_secret or not sig:
            return False
        expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)

    # PAY-08: only these Razorpay events move money state. Every other event a
    # payment emits (payment.authorized, payment.downtime.*, subscription.*, …)
    # is ignored so one payment's event stream can't double-book from downstream
    # status inference. `payment_link_probe` events with no `event` key (bare
    # entity bodies used in tests) are allowed through.
    _RZP_MONEY_EVENTS = frozenset({
        "payment.captured",
        "payment.failed",
        "payment_link.paid",
        "order.paid",
        "refund.processed",
        "refund.created",
        "refund.failed",
    })

    def parse_webhook(self, *, body: bytes) -> WebhookEvent | None:
        data = _json_body(body)
        if not data:
            return None
        event = str(data.get("event") or "").strip().lower()
        if event and event not in self._RZP_MONEY_EVENTS:
            return None
        payload = data.get("payload") or data
        payment = (payload.get("payment") or {}).get("entity") or payload.get("payment") or payload
        link = (payload.get("payment_link") or {}).get("entity") or payload.get("payment_link") or {}
        refund = (payload.get("refund") or {}).get("entity") or payload.get("refund") or {}

        def _paise(raw) -> Decimal:
            # BB-000413: Razorpay amounts are always paise — normalize any JSON type.
            try:
                return (Decimal(str(raw or 0)) / Decimal("100")).quantize(Decimal("0.01"))
            except Exception:
                return Decimal("0")

        fee = _paise(payment.get("fee"))

        # B4-004 / B4-005: classify by the Razorpay *event name*, not by inferring
        # from the payment entity's status. A `refund.*` event's `payment.amount`
        # is the whole captured amount — reading it as the refund amount makes a
        # partial refund look like a full unwind. Only bare probe bodies (no
        # `event` key) fall back to entity-status inference.
        if event.startswith("refund."):
            status = "REFUNDED"
            amount = _paise(refund.get("amount"))
            provider_payment_id = str(
                refund.get("payment_id") or payment.get("id") or data.get("id") or ""
            )
        elif event == "payment.failed":
            status = "FAILED"
            amount = _paise(payment.get("amount") or data.get("amount"))
            provider_payment_id = str(payment.get("id") or data.get("id") or "")
        elif event in ("payment.captured", "payment_link.paid", "order.paid"):
            status = "CAPTURED"
            amount = _paise(payment.get("amount") or data.get("amount"))
            provider_payment_id = str(payment.get("id") or data.get("id") or "")
        else:
            # bare entity probe body — no event name
            status_map = {
                "captured": "CAPTURED",
                "paid": "CAPTURED",
                "failed": "FAILED",
                "refunded": "REFUNDED",
            }
            st = str(payment.get("status") or data.get("status") or "").lower()
            status = status_map.get(st, st.upper())
            amount = _paise(payment.get("amount") or data.get("amount"))
            provider_payment_id = str(payment.get("id") or data.get("id") or "")

        return WebhookEvent(
            provider_payment_id=provider_payment_id,
            amount=amount,
            fee=fee,
            status=status,
            payment_link_id=str(link.get("id") or data.get("payment_link_id") or ""),
            raw=data,
        )

    def refund(self, *, provider_payment_id: str, amount: Decimal, idempotency_key: str = "") -> dict[str, Any]:
        idempotency_key = idempotency_key or _stable_refund_key(provider_payment_id, amount)
        if not self.key_id or not self.key_secret:
            raise BusinessRuleError("Razorpay credentials are not configured.")
        import base64

        import requests

        auth = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode()).decode()
        amount_paise = int(Decimal(amount).quantize(Decimal("0.01")) * 100)
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        if idempotency_key:
            headers["X-Razorpay-Idempotency-Key"] = idempotency_key[:64]
        body = {"amount": amount_paise}
        if idempotency_key:
            body["receipt"] = idempotency_key[:40]
        resp = requests.post(
            f"https://api.razorpay.com/v1/payments/{provider_payment_id}/refund",
            headers=headers,
            json=body,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise BusinessRuleError(f"Razorpay refund failed (HTTP {resp.status_code}).")
        return resp.json()

    def cancel_payment_link(self, *, provider_link_id: str) -> None:
        if not self.key_id or not self.key_secret:
            raise BusinessRuleError("Razorpay credentials are not configured.")
        if not provider_link_id:
            raise BusinessRuleError("Missing Razorpay payment link id.")
        import base64

        import requests

        auth = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode()).decode()
        resp = requests.post(
            f"https://api.razorpay.com/v1/payment_links/{provider_link_id}/cancel",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise BusinessRuleError(
                f"Razorpay could not cancel payment link (HTTP {resp.status_code}). "
                "Deactivate it in the Razorpay dashboard if it is already paid or expired."
            )


def cashfree_order_id_for_refund(provider_payment_id: str, raw=None) -> str:
    """Cashfree refunds are POST /orders/{order_id}/refunds.

    Historical webhooks stored cf_payment_id as provider_payment_id; prefer
    cf_order_id / order_id from the captured webhook payload when present.
    """
    if isinstance(raw, dict):
        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        order = data.get("order") if isinstance(data.get("order"), dict) else {}
        oid = str(
            data.get("cf_order_id")
            or data.get("order_id")
            or order.get("order_id")
            or order.get("cf_order_id")
            or ""
        ).strip()
        if oid:
            return oid
    return (provider_payment_id or "").strip()


class CashfreeGateway:
    name = "cashfree"

    def __init__(self, credentials: dict[str, Any]):
        self.app_id = (credentials.get("app_id") or credentials.get("client_id") or "").strip()
        self.secret_key = (credentials.get("secret_key") or credentials.get("client_secret") or "").strip()
        self.webhook_secret = (credentials.get("webhook_secret") or "").strip()
        self.api_base = (credentials.get("api_base") or "https://api.cashfree.com/pg").rstrip("/")

    def create_payment_link(self, **kwargs) -> CreateLinkResult:
        if not self.app_id or not self.secret_key:
            raise BusinessRuleError("Cashfree credentials are not configured.")
        amount = kwargs["amount"]
        payload = {
            "link_id": kwargs.get("reference") or f"bb_{secrets.token_hex(6)}",
            "link_amount": float(format(Decimal(amount).quantize(Decimal("0.01")), "f")),
            "link_currency": "INR",
            "link_purpose": kwargs.get("description") or "Payment",
            "customer_details": {
                "customer_name": kwargs.get("customer_name") or "",
                "customer_email": kwargs.get("customer_email") or "",
                "customer_phone": kwargs.get("customer_phone") or "",
            },
            "link_notify": {"send_sms": False, "send_email": False},
            "link_meta": {"return_url": kwargs.get("callback_url") or ""},
        }
        import requests

        resp = requests.post(
            f"{self.api_base}/links",
            headers={
                "x-client-id": self.app_id,
                "x-client-secret": self.secret_key,
                "x-api-version": "2023-08-01",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise BusinessRuleError(
                f"Cashfree payment link failed (HTTP {resp.status_code}). Check credentials and retry."
            )
        data = resp.json()
        return CreateLinkResult(
            provider_link_id=str(data.get("link_id") or data.get("cf_link_id") or ""),
            short_url=str(data.get("link_url") or data.get("short_url") or ""),
            raw=data,
        )

    def cancel_payment_link(self, *, provider_link_id: str) -> None:
        if not self.app_id or not self.secret_key:
            raise BusinessRuleError("Cashfree credentials are not configured.")
        if not provider_link_id:
            raise BusinessRuleError("Missing Cashfree payment link id.")
        import requests

        resp = requests.post(
            f"{self.api_base}/links/{provider_link_id}/cancel",
            headers={
                "x-client-id": self.app_id,
                "x-client-secret": self.secret_key,
                "x-api-version": "2023-08-01",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            raise BusinessRuleError(
                f"Cashfree could not cancel payment link (HTTP {resp.status_code}). "
                "Deactivate it in the Cashfree dashboard if needed."
            )

    def verify_webhook(self, *, headers: dict[str, str], body: bytes) -> bool:
        sig = headers.get("x-webhook-signature") or headers.get("X-Webhook-Signature") or ""
        ts = headers.get("x-webhook-timestamp") or headers.get("X-Webhook-Timestamp") or ""
        # PAY-01: fail closed on a dedicated webhook secret — do NOT fall back to
        # the API secret_key (Cashfree signs webhooks with a separate secret;
        # the Razorpay adapter refuses this same fallback, BB-000307).
        secret = self.webhook_secret
        if not secret or not sig or not ts:
            return False
        try:
            ts_int = int(float(ts))
        except (TypeError, ValueError):
            return False
        from datetime import datetime, timezone as dt_tz

        now = datetime.now(tz=dt_tz.utc).timestamp()
        # Cashfree documents unix milliseconds (13 digits); seconds are 10.
        ts_sec = ts_int / 1000.0 if ts_int > 10**12 else float(ts_int)
        if abs(now - ts_sec) > 300:
            return False
        signed = ts + body.decode("utf-8")
        digest = hmac.new(
            secret.encode(), signed.encode(), hashlib.sha256
        ).digest()
        import base64

        expected = base64.b64encode(digest).decode()
        return hmac.compare_digest(expected, sig)

    def parse_webhook(self, *, body: bytes) -> WebhookEvent | None:
        data = _json_body(body)
        if not data:
            return None
        link = data.get("data") or data
        payment = {}
        if isinstance(link, dict):
            payment = link.get("payment") or {}
        if not isinstance(payment, dict):
            payment = {}
        if not isinstance(link, dict):
            link = {}
        order = link.get("order") if isinstance(link.get("order"), dict) else {}
        amount_raw = (
            payment.get("payment_amount")
            or payment.get("amount")
            or order.get("order_amount")
            or link.get("payment_amount")
            or link.get("order_amount")
            or link.get("link_amount")
            or link.get("amount")
            or "0"
        )
        amount = Decimal(str(amount_raw)).quantize(Decimal("0.01"))
        status_raw = str(
            payment.get("payment_status")
            or link.get("link_status")
            or link.get("order_status")
            or order.get("order_status")
            or ""
        ).upper()
        status_map = {"PAID": "CAPTURED", "SUCCESS": "CAPTURED", "FAILED": "FAILED", "REFUNDED": "REFUNDED"}
        order_id = str(
            link.get("cf_order_id")
            or link.get("order_id")
            or order.get("order_id")
            or order.get("cf_order_id")
            or ""
        )
        payment_id = str(
            payment.get("cf_payment_id")
            or payment.get("payment_id")
            or link.get("cf_payment_id")
            or link.get("payment_id")
            or ""
        )
        # Refunds are POST /orders/{order_id}/refunds — persist order id, not cf_payment_id.
        return WebhookEvent(
            provider_payment_id=order_id or payment_id,
            amount=amount,
            fee=Decimal("0"),
            status=status_map.get(status_raw, status_raw),
            payment_link_id=str(link.get("link_id") or link.get("cf_link_id") or ""),
            raw=data,
        )

    def refund(self, *, provider_payment_id: str, amount: Decimal, idempotency_key: str = "", raw=None) -> dict[str, Any]:
        idempotency_key = idempotency_key or _stable_refund_key(provider_payment_id, amount)
        if not self.app_id or not self.secret_key:
            raise BusinessRuleError("Cashfree credentials are not configured.")
        import requests

        order_id = cashfree_order_id_for_refund(provider_payment_id, raw)
        refund_amount = str(Decimal(amount).quantize(Decimal("0.01")))
        refund_id = (idempotency_key or f"bb_rf_{secrets.token_hex(8)}")[:40]
        resp = requests.post(
            f"{self.api_base}/orders/{order_id}/refunds",
            headers={
                "x-client-id": self.app_id,
                "x-client-secret": self.secret_key,
                "x-api-version": "2023-08-01",
                "Content-Type": "application/json",
            },
            json={"refund_amount": refund_amount, "refund_id": refund_id, "refund_note": "Bizboard refund"},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise BusinessRuleError(f"Cashfree refund failed (HTTP {resp.status_code}).")
        try:
            return resp.json()
        except ValueError as exc:
            raise BusinessRuleError("Cashfree refund returned invalid JSON.") from exc


class PayUGateway:
    name = "payu"

    def __init__(self, credentials: dict[str, Any]):
        self.merchant_key = (credentials.get("merchant_key") or credentials.get("key") or "").strip()
        self.merchant_salt = (credentials.get("merchant_salt") or credentials.get("salt") or "").strip()
        from django.conf import settings

        env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
        default_base = "https://secure.payu.in" if env in ("production", "staging") else "https://test.payu.in"
        self._explicit_api_base = bool((credentials.get("api_base") or "").strip())
        self.api_base = (credentials.get("api_base") or default_base).rstrip("/")

    def create_payment_link(self, **kwargs) -> CreateLinkResult:
        from django.conf import settings

        env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
        if env in ("production", "staging") and not self._explicit_api_base:
            raise BusinessRuleError("PayU api_base is required in production (use https://secure.payu.in).")
        if not self.merchant_key or not self.merchant_salt:
            raise BusinessRuleError("PayU credentials are not configured.")
        amount = Decimal(kwargs["amount"]).quantize(Decimal("0.01"))
        txnid = kwargs.get("reference") or f"bb_{secrets.token_hex(8)}"
        productinfo = kwargs.get("description") or "Payment"
        firstname = kwargs.get("customer_name") or "Customer"
        email = kwargs.get("customer_email") or "noreply@bizboard.local"
        phone = kwargs.get("customer_phone") or "9999999999"
        # key|txnid|amount|productinfo|firstname|email|udf1..udf10|SALT
        # (10 empty udf fields → 11 pipes between email and SALT). The webhook
        # reverse hash in verify_webhook mirrors this exact sequence.
        hash_seq = (
            f"{self.merchant_key}|{txnid}|{amount}|{productinfo}|{firstname}|{email}"
            + "|" * 11
            + self.merchant_salt
        )
        payu_hash = hashlib.sha512(hash_seq.encode()).hexdigest()
        payload = {
            "key": self.merchant_key,
            "txnid": txnid,
            "amount": str(amount),
            "productinfo": productinfo,
            "firstname": firstname,
            "email": email,
            "phone": phone,
            "surl": kwargs.get("callback_url") or "",
            "furl": kwargs.get("callback_url") or "",
            "hash": payu_hash,
        }
        import requests

        # PAY-03: prefer PayU's v2 Payment Links REST API (Basic auth, JSON
        # response with a real shareable URL). Fall back to the legacy hosted
        # checkout form-post for merchant accounts without Payment Links.
        # NOTE: verify the request/response shape against a live PayU merchant
        # account before enabling this provider in production.
        links_base = self.api_base.replace("secure.payu.in", "info.payu.in")
        try:
            lr = requests.post(
                f"{links_base}/payment-links",
                json={
                    "subAmount": str(amount),
                    "description": productinfo,
                    "source": "API",
                    "isPartialPaymentAllowed": False,
                    "transactionId": txnid,
                    "customer": {"name": firstname, "email": email, "phone": phone},
                    "successURL": kwargs.get("callback_url") or "",
                    "failureURL": kwargs.get("callback_url") or "",
                },
                auth=(self.merchant_key, self.merchant_salt),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise BusinessRuleError(f"PayU payment link request failed: {exc}") from exc
        if lr.status_code < 400:
            try:
                data = lr.json()
            except ValueError:
                data = {}
            result = (data.get("result") or data.get("paymentLink") or data) if isinstance(data, dict) else {}
            url = (
                result.get("paymentLink")
                or result.get("paymentLinkUrl")
                or result.get("shortUrl")
                or ""
            )
            link_id = str(result.get("invoiceNumber") or result.get("id") or txnid)
            if url:
                return CreateLinkResult(provider_link_id=link_id, short_url=url, raw=data)
        elif lr.status_code not in (404, 405, 501):
            raise BusinessRuleError(f"PayU payment link failed (HTTP {lr.status_code}).")

        resp = requests.post(f"{self.api_base}/_payment", data=payload, timeout=30)
        if resp.status_code >= 400:
            raise BusinessRuleError(f"PayU payment link failed (HTTP {resp.status_code}).")
        short_url = resp.url if resp.url else f"{self.api_base}/_payment?txnid={txnid}"
        return CreateLinkResult(provider_link_id=txnid, short_url=short_url, raw={"payload": payload})

    def cancel_payment_link(self, *, provider_link_id: str) -> None:
        raise BusinessRuleError(
            "PayU payment links cannot be cancelled from BizBoard. "
            "Expire or deactivate the transaction in PayU first."
        )

    def verify_webhook(self, *, headers: dict[str, str], body: bytes) -> bool:
        if not self.merchant_salt:
            return False
        data = _payu_body(body)
        if not data:
            return False
        status_val = str(data.get("status") or "")
        email = str(data.get("email") or "")
        firstname = str(data.get("firstname") or "")
        productinfo = str(data.get("productinfo") or "")
        amount = str(data.get("amount") or "")
        txnid = str(data.get("txnid") or "")
        received = str(data.get("hash") or "").strip().lower()
        if not received:
            return False
        udf = [str(data.get(f"udf{i}") or "") for i in range(1, 11)]
        # PAY-04: reverse hash is the request sequence mirrored —
        #   SALT|status|udf10|…|udf1|email|firstname|productinfo|amount|txnid|key
        # If PayU echoes `additionalCharges`, it is prepended to the sequence.
        # NOTE: PayU has several hash layouts by integration version — verify
        # against a live merchant account before enabling this provider.
        rev_udf = "|".join(reversed(udf))
        seq = (
            f"{self.merchant_salt}|{status_val}|{rev_udf}|{email}|{firstname}|"
            f"{productinfo}|{amount}|{txnid}|{self.merchant_key}"
        )
        add_charges = str(data.get("additionalCharges") or "").strip()
        candidates = [seq]
        if add_charges:
            candidates.append(f"{add_charges}|{seq}")
        for cand in candidates:
            expected = hashlib.sha512(cand.encode()).hexdigest()
            if hmac.compare_digest(expected, received):
                return True
        return False

    def parse_webhook(self, *, body: bytes) -> WebhookEvent | None:
        data = _payu_body(body)
        if not data:
            return None
        amount = Decimal(str(data.get("amount") or "0")).quantize(Decimal("0.01"))
        status_raw = str(data.get("status") or "failed").lower()
        status_map = {"success": "CAPTURED", "captured": "CAPTURED", "failed": "FAILED", "refunded": "REFUNDED"}
        return WebhookEvent(
            provider_payment_id=str(data.get("mihpayid") or data.get("payment_id") or ""),
            amount=amount,
            fee=Decimal("0"),
            status=status_map.get(status_raw, status_raw.upper()),
            payment_link_id=str(data.get("txnid") or data.get("productinfo") or ""),
            raw=data,
        )

    def refund(self, *, provider_payment_id: str, amount: Decimal, idempotency_key: str = "") -> dict[str, Any]:
        idempotency_key = idempotency_key or _stable_refund_key(provider_payment_id, amount)
        if not self.merchant_key or not self.merchant_salt:
            raise BusinessRuleError("PayU credentials are not configured.")
        import requests

        refund_amount = str(Decimal(amount).quantize(Decimal("0.01")))
        command = "cancel_refund_transaction"
        hash_seq = f"{self.merchant_key}|{command}|{provider_payment_id}|{self.merchant_salt}"
        payu_hash = hashlib.sha512(hash_seq.encode()).hexdigest()
        payload = {
            "key": self.merchant_key,
            "command": command,
            "var1": provider_payment_id,
            "var2": refund_amount,
            # cancel_refund_transaction: var3 is the merchant token. Pass the
            # stable idempotency_key so retries are unique-but-stable and a
            # double-submit is less likely to create a second refund.
            "var3": (idempotency_key or "")[:64],
            "hash": payu_hash,
        }
        resp = requests.post(
            f"{self.api_base}/merchant/postservice?form=2",
            data=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise BusinessRuleError(f"PayU refund failed (HTTP {resp.status_code}).")
        try:
            data = resp.json()
        except ValueError as exc:
            raise BusinessRuleError("PayU refund returned invalid JSON.") from exc
        status_val = str(data.get("status") or data.get("Status") or "").lower()
        if status_val in ("0", "failed", "failure", "error"):
            msg = data.get("msg") or data.get("message") or "PayU refund rejected."
            raise BusinessRuleError(str(msg))
        return data


class _DisabledProviderAdapter:
    """Fail-closed stub for Cashfree/PayU until real integrations ship."""

    def __init__(self, name: str):
        self.name = name

    def create_payment_link(self, **kwargs) -> CreateLinkResult:
        raise BusinessRuleError(
            f"Payment provider '{self.name}' is not enabled. Use sandbox (test) or razorpay."
        )

    def verify_webhook(self, *, headers: dict[str, str], body: bytes) -> bool:
        return False

    def parse_webhook(self, *, body: bytes) -> WebhookEvent | None:
        # Allow parse for probe identity only; verify always fails.
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None
        return WebhookEvent(
            provider_payment_id=str(data.get("payment_id") or data.get("id") or ""),
            amount=Decimal(str(data.get("amount") or data.get("order_amount") or "0")),
            fee=Decimal("0"),
            status="FAILED",
            payment_link_id=str(data.get("payment_link_id") or data.get("link_id") or data.get("productinfo") or ""),
            raw=data,
        )

    def refund(self, *, provider_payment_id: str, amount: Decimal, idempotency_key: str = "") -> dict[str, Any]:
        idempotency_key = idempotency_key or _stable_refund_key(provider_payment_id, amount)
        raise BusinessRuleError(f"Payment provider '{self.name}' is not enabled.")


def _settings_gateway_credentials(provider: str) -> dict[str, Any]:
    from django.conf import settings

    if provider == "cashfree":
        return {
            "app_id": getattr(settings, "CASHFREE_APP_ID", "") or "",
            "secret_key": getattr(settings, "CASHFREE_SECRET_KEY", "") or "",
            "webhook_secret": getattr(settings, "CASHFREE_WEBHOOK_SECRET", "") or "",
        }
    if provider == "payu":
        return {
            "merchant_key": getattr(settings, "PAYU_MERCHANT_KEY", "") or "",
            "merchant_salt": getattr(settings, "PAYU_MERCHANT_SALT", "") or "",
        }
    return {}


def parse_webhook_probe(provider: str, body: bytes) -> WebhookEvent | None:
    """Parse payment_link_id from payload without trusting credentials."""
    provider = (provider or "").lower().strip()
    try:
        if provider == "sandbox":
            return SandboxAdapter().parse_webhook(body=body)
        if provider == "razorpay":
            return RazorpayAdapter({}).parse_webhook(body=body)
        if provider == "cashfree":
            return CashfreeGateway({}).parse_webhook(body=body)
        if provider == "payu":
            return PayUGateway({}).parse_webhook(body=body)
        if provider in DISABLED_PROVIDERS:
            return _DisabledProviderAdapter(provider).parse_webhook(body=body)
    except Exception:
        return None
    return None


def sandbox_forbidden_env() -> bool:
    """Sandbox create/settle allowed only in development/test/local.

    Unset or unknown DJANGO_ENV is treated as production-safe (sandbox forbidden).
    """
    from django.conf import settings

    django_env = (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()
    return django_env not in _SANDBOX_ALLOWED_ENVS


def get_adapter(
    provider: str,
    credentials: dict[str, Any] | None = None,
    *,
    company_id=None,
) -> PaymentGatewayAdapter:
    """Return adapter for provider. Sandbox only when provider == 'sandbox' explicitly."""
    provider = (provider or "razorpay").lower().strip()
    creds = credentials or {}

    if provider == "sandbox":
        if sandbox_forbidden_env():
            raise BusinessRuleError(
                "Payment provider 'sandbox' cannot be used outside development/test/local."
            )
        return SandboxAdapter(company_id=company_id)

    if provider in DISABLED_PROVIDERS:
        return _DisabledProviderAdapter(provider)

    if not creds:
        creds = _settings_gateway_credentials(provider)

    if not creds and provider not in ("sandbox",):
        raise BusinessRuleError(
            f"Payment provider '{provider}' requires credentials; sandbox fallback is disabled."
        )

    if provider == "razorpay":
        return RazorpayAdapter(creds)

    if provider == "cashfree":
        return CashfreeGateway(creds)

    if provider == "payu":
        return PayUGateway(creds)

    raise BusinessRuleError(f"Unknown payment provider '{provider}'.")
