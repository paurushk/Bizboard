"""UPI intent / QR payload helpers (Phase 3.0)."""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote


def normalize_utr(value: str | None) -> str:
    return (value or "").strip().upper().replace(" ", "")


def build_upi_intent(
    *,
    upi_id: str,
    amount: Decimal | None = None,
    note: str = "",
    payee_name: str = "",
) -> str:
    """Build an amount-locked UPI deep link (`upi://pay?...`)."""
    upi_id = (upi_id or "").strip()
    if not upi_id:
        return ""
    parts = [f"pa={quote(upi_id, safe='@.')}", "cu=INR"]
    if payee_name:
        parts.append(f"pn={quote(payee_name[:50])}")
    if amount is not None and Decimal(amount) > 0:
        parts.append(f"am={Decimal(amount).quantize(Decimal('0.01'))}")
    if note:
        parts.append(f"tn={quote(note[:40])}")
    return "upi://pay?" + "&".join(parts)


def upi_qr_fields(*, upi_id: str, amount: Decimal | None = None, note: str = "", payee_name: str = "") -> dict:
    intent = build_upi_intent(upi_id=upi_id, amount=amount, note=note, payee_name=payee_name)
    qr_b64 = ""
    if intent:
        import base64
        from io import BytesIO

        import qrcode

        qr = qrcode.QRCode(version=None, box_size=4, border=2)
        qr.add_data(intent)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return {
        "upi_id": (upi_id or "").strip(),
        "amount": str(Decimal(amount).quantize(Decimal("0.01"))) if amount is not None else None,
        "note": (note or "")[:40],
        "intent_url": intent,
        "amount_locked": amount is not None and Decimal(amount) > 0,
        "qr_png_base64": qr_b64,
    }
