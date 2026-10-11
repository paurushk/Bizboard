"""Money In domain-event handlers.

Run synchronously inside the emitting transaction; ``core.events.emit`` swallows their errors, so
each one works inside its own savepoint to keep a database error from poisoning the receipt's
transaction.
"""

from __future__ import annotations

import logging

from django.db import transaction

from core.events import subscribe

logger = logging.getLogger(__name__)


@subscribe("customer_receipt.created")
def close_promises_on_receipt(*, receipt, user=None, **kwargs):
    """A kept promise to pay closes at once, not at the next evaluation."""
    from .promise_to_pay import close_kept_promises

    with transaction.atomic():
        close_kept_promises(receipt.company, receipt.customer, receipt=receipt, user=user)


@subscribe("customer_receipt.voided")
def reopen_promises_and_links_on_void(*, receipt, user=None, **kwargs):
    """A voided receipt re-opens what it had closed: promises, and a payment link marked paid."""
    from .models import GatewayPayment, GatewayPaymentStatus, PaymentLink, PaymentLinkStatus
    from .promise_to_pay import reopen_unkept_promises

    with transaction.atomic():
        reopen_unkept_promises(receipt, user=user)
        for link in PaymentLink.objects.filter(company=receipt.company, paid_receipt=receipt):
            captured = GatewayPayment.objects.filter(
                payment_link=link, status=GatewayPaymentStatus.CAPTURED
            ).exists()
            if captured:
                # Money really moved through the gateway: only a person can decide what that
                # means for the link, so say so instead of quietly re-opening it.
                _flag_link_for_review(link, receipt, user)
                continue
            link.status = PaymentLinkStatus.SENT
            link.paid_receipt = None
            link.updated_by = user
            link.save(update_fields=["status", "paid_receipt", "updated_by", "updated_at"])


def _flag_link_for_review(link, receipt, user) -> None:
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService

    for membership in CompanyUser.objects.filter(
        company=link.company, is_active=True, role=CompanyUser.Role.OWNER
    ).select_related("user"):
        NotificationService.send(
            company=link.company,
            channel=Notification.Channel.IN_APP,
            recipient=membership.user.email or str(membership.user_id),
            subject="Payment link needs a look",
            body=(
                f"Receipt {receipt.number or receipt.pk} was voided but a gateway capture exists "
                f"for payment link {link.pk}. Check the payment before collecting again."
            ),
            user=membership.user,
        )
