"""WhatsApp Cloud API client with explicit wa.me fallback (Wave 17E / Sprint 5)."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

import requests

from core.services.feature_flags import build_feature_flags

APPROVED_WHATSAPP_TEMPLATES = frozenset({
    "invoice_ready",
    "payment_reminder",
    "invoice_share",
})


@dataclass
class WhatsAppSendResult:
    mode: str  # "cloud" | "link"
    share_link: str = ""
    message_id: str = ""
    raw: dict | None = None


def _normalize_phone(to_phone: str) -> str:
    return "".join(c for c in (to_phone or "") if c.isdigit())


def _wa_me_link(*, phone: str, text: str) -> str:
    return f"https://wa.me/{phone}?text={quote(text[:1000])}"


def _format_template_body(template_name: str, params: list[str] | dict | None) -> str:
    if isinstance(params, dict):
        parts = [str(v) for v in params.values() if v is not None]
    elif isinstance(params, list):
        parts = [str(v) for v in params if v is not None]
    else:
        parts = []
    if parts:
        return f"{template_name}: " + " | ".join(parts)
    return template_name


def _resolve_whatsapp_credentials(company=None) -> tuple[str, str]:
    """Per-company IntegrationConnection only — never a process-wide token (BB-000571)."""
    if company is None:
        return "", ""
    try:
        from integrations.models import IntegrationConnection

        from core.services.gsp_secrets import decrypt_gsp_credentials

        conn = IntegrationConnection.objects.filter(
            company=company,
            provider=IntegrationConnection.Provider.WHATSAPP,
            status=IntegrationConnection.Status.ACTIVE,
        ).first()
        if not conn or not (conn.encrypted_secrets or "").strip():
            return "", ""
        creds = decrypt_gsp_credentials(conn.encrypted_secrets)
        token = (
            creds.get("token")
            or creds.get("access_token")
            or creds.get("whatsapp_token")
            or ""
        ).strip()
        phone_number_id = (
            creds.get("phone_number_id")
            or creds.get("phoneNumberId")
            or creds.get("whatsapp_phone_number_id")
            or ""
        ).strip()
        return token, phone_number_id
    except Exception:
        logger.warning("WhatsApp credential decrypt failed; falling back to wa.me", exc_info=True)
        return "", ""


def send_whatsapp_template(
    to_phone: str,
    template_name: str,
    params: list[str] | dict | None = None,
    *,
    company=None,
    allow_cloud: bool = True,
) -> WhatsAppSendResult:
    """Send an approved WhatsApp template via Cloud API, else explicit wa.me link."""
    phone = _normalize_phone(to_phone)
    body_text = _format_template_body(template_name, params)
    link_result = WhatsAppSendResult(
        mode="link",
        share_link=_wa_me_link(phone=phone, text=body_text),
    )

    flags = build_feature_flags(company=company)
    if not allow_cloud or not flags.get("ENABLE_WHATSAPP_CLOUD"):
        return link_result
    approved = {name.lower() for name in APPROVED_WHATSAPP_TEMPLATES}
    if (template_name or "").strip().lower() not in approved:
        return link_result

    token, phone_number_id = _resolve_whatsapp_credentials(company)
    if not token or not phone_number_id or not phone:
        return link_result

    components = []
    if params:
        if isinstance(params, dict):
            param_values = list(params.values())
        else:
            param_values = list(params)
        if param_values:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(v)} for v in param_values],
                }
            )

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            **({"components": components} if components else {}),
        },
    }
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        return WhatsAppSendResult(
            mode="link",
            share_link=_wa_me_link(phone=phone, text=body_text),
            raw={"error": resp.text, "status_code": resp.status_code},
        )
    data = resp.json()
    messages = data.get("messages") or []
    if not messages:
        return WhatsAppSendResult(
            mode="link",
            share_link=_wa_me_link(phone=phone, text=body_text),
            raw={**data, "error": "WhatsApp Cloud returned no messages."},
        )
    message_id = str(messages[0].get("id") or "")
    if not message_id:
        return WhatsAppSendResult(
            mode="link",
            share_link=_wa_me_link(phone=phone, text=body_text),
            raw={**data, "error": "WhatsApp Cloud returned no message id."},
        )
    return WhatsAppSendResult(mode="cloud", message_id=message_id, raw=data)
