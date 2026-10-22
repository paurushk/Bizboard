"""WP-CM2: every SMS and WhatsApp message comes from one registered template.

Indian operators drop SMS that do not match a DLT-registered template, so a body built inline in
some caller would silently never arrive. Every SMS is sent with ``SmsProvider.send_template(phone,
key, **vars)``; the guard ``guard_message_templates`` fails CI on any other send.

``dlt_setting`` names the Django setting holding the DLT template ID (filled once DLT registration
is done, handover item 6). In staging/production a template with no DLT ID is refused for Indian
numbers, the same rule ``_send_msg91`` already applied to the OTP. ``body`` must match the text
registered with DLT word for word, with ``{name}`` for each DLT variable.

WhatsApp templates are approved in Meta's manager; only names listed here may be sent.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from core.exceptions import BusinessRuleError

# DLT allows up to 2000 characters, but a single SMS part is 160; keep reminders to two parts.
MAX_SMS_LENGTH = 320


@dataclass(frozen=True)
class SmsTemplate:
    key: str
    body: str
    dlt_setting: str
    variables: tuple[str, ...]

    def dlt_template_id(self) -> str:
        return (getattr(settings, self.dlt_setting, "") or "").strip()

    def render(self, **values) -> str:
        missing = [v for v in self.variables if v not in values]
        if missing:
            raise BusinessRuleError(f"SMS template '{self.key}' is missing {', '.join(missing)}.")
        text = self.body.format(**{k: values[k] for k in self.variables})
        return text[:MAX_SMS_LENGTH]


SMS_TEMPLATES: dict[str, SmsTemplate] = {
    t.key: t
    for t in (
        SmsTemplate(
            key="otp",
            body="Your BizBoard OTP is {code}",
            dlt_setting="MSG91_TEMPLATE_ID",
            variables=("code",),
        ),
        SmsTemplate(
            key="payment_reminder",
            body="Payment reminder from {company}: invoice {number} for INR {amount} was due on {due_date}. Please pay.",
            dlt_setting="SMS_DLT_TEMPLATE_PAYMENT_REMINDER",
            variables=("company", "number", "amount", "due_date"),
        ),
    )
}

# GD-25: the invoice that carries a payment link is the first template; payment_reminder is not a
# campaign send.
WHATSAPP_TEMPLATES: frozenset[str] = frozenset({
    "invoice_with_payment_link",
    "invoice_ready",
    "payment_reminder",
    "invoice_share",
})


def sms_template(key: str) -> SmsTemplate:
    try:
        return SMS_TEMPLATES[key]
    except KeyError as exc:
        raise BusinessRuleError(f"'{key}' is not a registered SMS template.") from exc
