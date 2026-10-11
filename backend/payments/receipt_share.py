"""Sharing a receipt voucher with the customer: a signed, expiring link and the message text.

The person receiving it has no login, so the message carries a link that opens the PDF. The link is
a signed token (company, receipt, expiry): nothing is stored, nothing can be guessed, and a voided
receipt stops resolving. Sending is logged on the receipt.
"""

from __future__ import annotations

from django.core import signing
from django.utils import timezone

SALT = "bizboard.receipt-voucher"
LINK_MAX_AGE_SECONDS = 30 * 24 * 3600


def mint_voucher_token(receipt) -> str:
    return signing.dumps({"r": receipt.pk, "c": receipt.company_id}, salt=SALT, compress=True)


def read_voucher_token(token: str):
    """(receipt_id, company_id) or None when the token is bad or older than 30 days."""
    try:
        data = signing.loads(token, salt=SALT, max_age=LINK_MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None
    try:
        return int(data["r"]), int(data["c"])
    except (KeyError, TypeError, ValueError):
        return None


def public_voucher_url(receipt, request=None) -> str:
    from payments.webhook_views import public_frontend_base_url

    path = f"/api/v1/public/receipt-voucher/{mint_voucher_token(receipt)}/"
    if request is not None:
        return request.build_absolute_uri(path)
    try:
        return f"{public_frontend_base_url().rstrip('/')}{path}"
    except Exception:  # noqa: BLE001 - no FRONTEND_URL configured: a relative path still works
        return path


def compose_receipt_message(receipt, url: str) -> str:
    company = receipt.company
    return (
        f"Receipt {receipt.number} dated {receipt.receipt_date} from {company.name}. "
        f"Amount received: INR {receipt.amount}. View the receipt: {url}"
    )


def sent_at_label() -> str:
    return timezone.now().isoformat()
