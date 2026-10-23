"""WP-BL4: UPI Autopay renewals.

Razorpay's hosted subscription checkout offers UPI Autopay next to cards when it is enabled on the
account; the customer authorises a mandate there. Mandate events arrive on the existing webhook:
``subscription.authenticated`` (mandate approved), ``.activated``/``.charged`` (renewal paid,
invoiced by WP-BL2), ``.pending``/``.halted`` (debit failing → PAST_DUE → SaaS dunning),
``.paused``/``.resumed``, ``.cancelled``. Events the webhook does not understand are parked on
the dead-letter queue.

The statutory pre-debit notice and the pause/opt-out link are sent by the bank/NPCI rail, not by
us. Bizboard's own reminder is **email only** (category ``billing``), 3 days before the renewal,
once per cycle — no SMS, so it neither duplicates the statutory SMS nor spends SMS budget (AB1).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

REMINDER_DAYS = 3
MANDATE_EVENTS = {
    "subscription.authenticated": "AUTHENTICATED",
    "subscription.activated": "ACTIVE",
    "subscription.charged": "ACTIVE",
    "subscription.resumed": "ACTIVE",
    "subscription.pending": "FAILING",
    "subscription.halted": "HALTED",
    "subscription.paused": "PAUSED",
    "subscription.cancelled": "CANCELLED",
    "subscription.completed": "CANCELLED",
}
# Events the webhook applies; any other ``subscription.*`` event is parked before it is applied.
HANDLED_EVENTS = {*MANDATE_EVENTS, "subscription.updated"}


def record_mandate_event(sub, payload: dict) -> None:
    """Keep the mandate state and the payment method of the last charge on the subscription."""
    event = str(payload.get("event") or "")
    state = MANDATE_EVENTS.get(event)
    if state is None:
        return
    fields = []
    if sub.mandate_status != state:
        sub.mandate_status = state
        fields.append("mandate_status")
    payment = ((((payload.get("payload") or {}).get("payment") or {}).get("entity")) or {})
    method = str(payment.get("method") or "").lower()
    if method in ("upi", "card", "emandate", "nach") and sub.payment_method != method:
        sub.payment_method = method
        fields.append("payment_method")
    if fields:
        sub.save(update_fields=[*fields, "updated_at"])


def send_renewal_reminders(now=None) -> int:
    """Daily: email the owner 3 days before an automatic renewal, once per cycle. Never SMS."""
    from core.mail import Suppressed, send
    from core.rls import rls_bypass

    from .models import Subscription

    now = now or timezone.now()
    # Renewals due within the next REMINDER_DAYS local days, not yet reminded for this period end:
    # a day the task missed (or a send that failed) is caught up the next day instead of skipped.
    last_day = timezone.localdate(now + timedelta(days=REMINDER_DAYS))
    sent = 0
    with rls_bypass():
        due = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, current_period_end__gt=now,
            current_period_end__date__lte=last_day,
        ).exclude(razorpay_subscription_id="").select_related("company", "plan", "pending_plan")
        for sub in due:
            if sub.renewal_reminder_for == sub.current_period_end:
                continue
            to = getattr(sub.company, "email", "") or ""
            if not to:
                continue
            # A switch waiting for this renewal is what will be charged then.
            renewing = sub.pending_plan if sub.pending_plan_id and sub.pending_authenticated_at else sub.plan
            how = {"upi": "UPI Autopay", "card": "your saved card"}.get(sub.payment_method, "your saved payment method")
            amount = f"₹{(renewing.price_paise or 0) / 100:,.2f}"
            try:
                send(
                    to=to, category="billing",
                    subject=f"Your Bizboard plan renews on {timezone.localtime(sub.current_period_end):%d %b %Y}",
                    body=(f"Your {renewing.name} plan renews on "
                          f"{timezone.localtime(sub.current_period_end):%d %b %Y}. {amount} (GST included) will be "
                          f"collected through {how}; your bank or UPI app may also send its own notice. "
                          "To change or cancel, open Settings → Billing in Bizboard."),
                )
            except Suppressed:
                pass
            except Exception:  # noqa: BLE001 - one failed send must not skip the rest; retried tomorrow
                logger.exception("Renewal reminder for subscription %s failed", sub.pk)
                continue
            sub.renewal_reminder_for = sub.current_period_end
            sub.save(update_fields=["renewal_reminder_for", "updated_at"])
            sent += 1
    return sent
