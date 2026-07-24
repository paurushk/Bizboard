"""PDF helpers — amount in words, tax breakup, UPI QR."""

from __future__ import annotations

import io
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digits(n: int) -> str:
    if n < 20:
        return ONES[n]
    return f"{TENS[n // 10]}{(' ' + ONES[n % 10]) if n % 10 else ''}".strip()


def _three_digits(n: int) -> str:
    if n < 100:
        return _two_digits(n)
    hundred = ONES[n // 100]
    rest = n % 100
    if rest:
        return f"{hundred} Hundred {_two_digits(rest)}"
    return f"{hundred} Hundred"


def amount_in_words(value: Decimal | int | float | str) -> str:
    """Indian numbering: Crore / Lakh / Thousand. Returns e.g. 'One Hundred Rupees Only'."""
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < 0:
        amount = abs(amount)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)

    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        crore = rupees // 10000000
        rupees %= 10000000
        lakh = rupees // 100000
        rupees %= 100000
        thousand = rupees // 1000
        rupees %= 1000
        if crore:
            parts.append(f"{_three_digits(crore)} Crore")
        if lakh:
            parts.append(f"{_three_digits(lakh)} Lakh")
        if thousand:
            parts.append(f"{_three_digits(thousand)} Thousand")
        if rupees:
            parts.append(_three_digits(rupees))
        words = " ".join(parts)

    result = f"{words} Rupees"
    if paise:
        result += f" and {_two_digits(paise)} Paise"
    return f"{result} Only"


def tax_breakup_by_rate(items, *, tax_enabled: bool = True) -> list[dict]:
    """
    Group line tax into CGST/SGST half-rates or IGST full rates.

    Returns sorted list of:
      {"label": "CGST@9", "amount": Decimal(...)} etc.
    """
    if not tax_enabled:
        return []

    cgst_by_half: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0"))
    sgst_by_half: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0"))
    igst_by_rate: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0"))

    for item in items:
        rate = Decimal(item.gst_rate)
        half = (rate / 2).quantize(Decimal("0.01"))
        cgst = Decimal(item.cgst or 0)
        sgst = Decimal(item.sgst or 0)
        igst = Decimal(item.igst or 0)
        if cgst:
            cgst_by_half[half] += cgst
        if sgst:
            sgst_by_half[half] += sgst
        if igst:
            igst_by_rate[rate] += igst

    rows: list[dict] = []
    for half in sorted(set(cgst_by_half) | set(sgst_by_half)):
        if cgst_by_half.get(half):
            rows.append({"label": f"CGST@{_fmt_rate(half)}", "amount": cgst_by_half[half]})
        if sgst_by_half.get(half):
            rows.append({"label": f"SGST@{_fmt_rate(half)}", "amount": sgst_by_half[half]})
    for rate in sorted(igst_by_rate):
        rows.append({"label": f"IGST@{_fmt_rate(rate)}", "amount": igst_by_rate[rate]})
    return rows


def _fmt_rate(rate: Decimal) -> str:
    if rate == rate.to_integral_value():
        return str(int(rate))
    return f"{rate.normalize()}"


def build_upi_qr_png(upi_id: str, amount: Decimal | None = None, note: str = "") -> bytes | None:
    """Build a UPI intent QR PNG. Returns None if upi_id is blank."""
    upi_id = (upi_id or "").strip()
    if not upi_id:
        return None
    params = [f"pa={upi_id}", "cu=INR"]
    if amount is not None and Decimal(amount) > 0:
        params.append(f"am={Decimal(amount).quantize(Decimal('0.01'))}")
    if note:
        params.append(f"tn={note[:40]}")
    payload = "upi://pay?" + "&".join(params)

    import qrcode

    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def format_money(value) -> str:
    return f"{Decimal(str(value or 0)):.2f}"


def format_qty(value) -> str:
    q = Decimal(str(value or 0))
    if q == q.to_integral_value():
        return f"{int(q)}.0"
    return f"{q.normalize()}"
