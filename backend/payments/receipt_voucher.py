"""Customer receipt voucher PDF (A4 or 80 mm thermal), in English or Hindi.

A voucher is an acknowledgement of money received. It is not a tax invoice. A voided
receipt is stamped VOIDED with the reason so a reprint can never pass as live money.

English uses the built-in Helvetica and prints amounts as "Rs." (that font has no rupee
sign). Hindi uses the bundled Noto Sans Devanagari (SIL OFL, see ``fonts/OFL.txt``), which
also carries the rupee sign and Latin letters, so customer names print in either script.
ReportLab cannot shape Devanagari, so Hindi text is shaped by HarfBuzz and drawn as vector
outlines (``shaped_text``); if the shaper or the font is unavailable the voucher is English.
"""

import logging
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from sales.pdf.helpers import amount_in_words, format_money

from .hindi_numbers import amount_in_words_hi
from .receipt_math import receipt_unallocated
from .shaped_text import ShapedFont, load_font, shaping_available

logger = logging.getLogger(__name__)

THERMAL_WIDTH = 226  # 80 mm in points
LAYOUTS = ("A4", "THERMAL")
LANGS = ("en", "hi")

_HI_FONT_PATH = Path(__file__).resolve().parent / "fonts" / "NotoSansDevanagari.ttf"
_hi_font_ok: bool | None = None

LABELS = {
    "en": {
        "title": "RECEIPT VOUCHER",
        "no": "No",
        "date": "Date",
        "from": "Received from",
        "mode": "Mode",
        "bank": "Bank",
        "utr": "UTR / ref",
        "reference": "Reference",
        "cheque": "Cheque",
        "cheque_date": "Cheque date",
        "cheque_status": "Cheque status",
        "amount": "Amount received",
        "discount": "Settlement discount",
        "discount_pending": "Settlement discount (applied when allocated)",
        "tds": "TDS deducted by customer",
        "refunds": "Advance refunds",
        "refund": "Refund",
        "gst_advance": "GST included in the advance",
        "taxable": "Taxable value",
        "applied": "Applied to invoices",
        "invoice": "Invoice",
        "advance": "Advance (not yet applied)",
        "voided": "VOIDED",
        "void_reason": "Void reason",
        "signatory": "Authorised signatory",
        "thanks": "Thank you",
        "gstin": "GSTIN",
        "phone": "Ph",
        "currency": "Rs.",
        "modes": {},
        "cheque_states": {},
    },
    "hi": {
        "title": "रसीद वाउचर",
        "no": "क्रमांक",
        "date": "दिनांक",
        "from": "प्राप्त किया",
        "mode": "माध्यम",
        "bank": "बैंक",
        "utr": "UTR / संदर्भ",
        "reference": "संदर्भ",
        "cheque": "चेक",
        "cheque_date": "चेक की तारीख",
        "cheque_status": "चेक की स्थिति",
        "amount": "प्राप्त राशि",
        "discount": "निपटान छूट",
        "discount_pending": "निपटान छूट (आवंटन पर लागू)",
        "tds": "ग्राहक द्वारा काटा गया TDS",
        "refunds": "लौटाए गए अग्रिम",
        "refund": "वापसी",
        "gst_advance": "अग्रिम में शामिल GST",
        "taxable": "कर योग्य मूल्य",
        "applied": "इन बिलों पर लगाई गई",
        "invoice": "बिल",
        "advance": "अग्रिम (अभी लगाया नहीं गया)",
        "voided": "रद्द",
        "void_reason": "रद्द करने का कारण",
        "signatory": "अधिकृत हस्ताक्षरकर्ता",
        "thanks": "धन्यवाद",
        "gstin": "GSTIN",
        "phone": "फोन",
        "currency": "₹",
        "modes": {
            "CASH": "नकद", "UPI": "UPI", "BANK": "बैंक", "CARD": "कार्ड", "CREDIT": "उधार", "CHEQUE": "चेक",
        },
        "cheque_states": {"PENDING_CLEARANCE": "लंबित", "CLEARED": "क्लियर", "BOUNCED": "बाउंस"},
    },
}


def hindi_font_available() -> bool:
    """True when the shaper is installed and the bundled font loads. Failure is logged once."""
    global _hi_font_ok
    if _hi_font_ok is None:
        try:
            if not shaping_available():
                raise RuntimeError("uharfbuzz is not installed")
            _hindi_fonts()
            _hi_font_ok = True
        except Exception:  # missing package/file or a bad font: print English rather than fail
            logger.exception("receipt_voucher.hindi_unavailable path=%s", _HI_FONT_PATH)
            _hi_font_ok = False
    return _hi_font_ok


def _hindi_fonts() -> tuple[ShapedFont, ShapedFont]:
    return load_font(str(_HI_FONT_PATH), 400), load_font(str(_HI_FONT_PATH), 700)


def needs_shaping(value: str) -> bool:
    """True for text Helvetica cannot print (anything beyond Latin-1)."""
    return any(ord(ch) > 255 for ch in value)


def _lines_for(receipt):
    rows = []
    for alloc in receipt.allocations.all():
        if alloc.reversed_at is not None:
            continue
        number = ""
        if alloc.sales_invoice_id:
            number = alloc.sales_invoice.number or f"#{alloc.sales_invoice_id}"
        rows.append((number, alloc.amount))
    return rows


def _payment_detail(receipt, labels) -> list[tuple[str, str]]:
    detail = [(labels["mode"], labels["modes"].get(receipt.mode, receipt.mode))]
    if receipt.bank_account_id:
        detail.append((labels["bank"], receipt.bank_account.name))
    if receipt.utr:
        detail.append((labels["utr"], receipt.utr))
    elif receipt.reference:
        detail.append((labels["reference"], receipt.reference))
    if receipt.mode == "CHEQUE":
        cheque = " ".join(part for part in (receipt.cheque_number, receipt.cheque_bank_name) if part)
        if cheque:
            detail.append((labels["cheque"], cheque))
        if receipt.cheque_date:
            detail.append((labels["cheque_date"], receipt.cheque_date.isoformat()))
        if receipt.cheque_status:
            state = labels["cheque_states"].get(
                receipt.cheque_status, receipt.cheque_status.replace("_", " ").title()
            )
            detail.append((labels["cheque_status"], state))
    return detail


def render_receipt_voucher_pdf(receipt, *, layout: str = "A4", lang: str = "en") -> bytes:
    layout = (layout or "A4").upper()
    if layout not in LAYOUTS:
        layout = "A4"
    lang = (lang or "en").lower()
    if lang not in LANGS or (lang == "hi" and not hindi_font_available()):
        lang = "en"
    labels = LABELS[lang]
    hindi = lang == "hi"
    hi_regular, hi_bold = _hindi_fonts() if hindi else (None, None)

    company = receipt.company
    allocation_rows = _lines_for(receipt)
    refund_rows = [
        (row.number or f"#{row.pk}", row.refund_date, row.amount)
        for row in receipt.advance_refunds.all()
        if row.status == "POSTED"
    ]
    # What the receipt still holds as an advance, counted exactly as the receipts screen does.
    advance = max(receipt_unallocated(receipt), Decimal("0"))
    discount_applied = sum(
        (alloc.discount_applied for alloc in receipt.allocations.all() if alloc.reversed_at is None),
        Decimal("0"),
    )
    discount_pending = bool(receipt.settlement_discount) and discount_applied < receipt.settlement_discount
    voided = receipt.status == "VOIDED"
    money = labels["currency"]

    thermal = layout == "THERMAL"
    # Thermal height grows with content; A4 is fixed and starts a new page when full.
    est_rows = len(allocation_rows) + len(refund_rows) + len(_payment_detail(receipt, labels)) + 3
    page_w = THERMAL_WIDTH if thermal else A4[0]
    page_h = max(380, 320 + 14 * est_rows) if thermal else A4[1]
    margin = 12 if thermal else 40
    right = page_w - margin
    size = 8 if thermal else 10

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(page_w, page_h))
    state = {"y": page_h - margin - 6}

    def need(space: float) -> None:
        if state["y"] - space < margin and not thermal:
            pdf.showPage()
            state["y"] = page_h - margin

    def measure(value, *, bold=False, font_size=None):
        """(width, shaped face or None, Helvetica name) for one string."""
        fs = font_size or size
        # Helvetica cannot print Devanagari (a customer named in Hindi on an English voucher
        # would come out as black boxes), so such a string is drawn with the shaped font.
        if hindi or (needs_shaping(value) and hindi_font_available()):
            face = (hi_bold if bold else hi_regular) or _hindi_fonts()[1 if bold else 0]
            return face.width(value, fs), face, None
        font = "Helvetica-Bold" if bold else "Helvetica"
        return pdfmetrics.stringWidth(value, font, fs), None, font

    def wrap(value, width, *, font_size=None):
        lines, current = [], ""
        for word in str(value).split():
            trial = f"{current} {word}".strip()
            if current and measure(trial, font_size=font_size)[0] > width:
                lines.append(current)
                current = word
            else:
                current = trial
        return lines + ([current] if current else [])

    def text(x, value, *, bold=False, font_size=None, align="left"):
        value = str(value)
        fs = font_size or size
        width, face, font = measure(value, bold=bold, font_size=fs)
        shaped = face is not None
        if align == "right":
            x = x - width
        elif align == "center":
            x = x - width / 2
        if shaped:
            face.draw(pdf, value, x, state["y"], fs)
        else:
            pdf.setFont(font, fs)
            pdf.drawString(x, state["y"], value)

    def down(step=None):
        state["y"] -= step if step is not None else size + 5

    def rule():
        pdf.setLineWidth(0.5)
        pdf.line(margin, state["y"] + 3, right, state["y"] + 3)
        down(6)

    title_size = 11 if thermal else 15
    centre = page_w / 2
    text(centre, company.legal_name or company.name, bold=True, font_size=title_size + 1, align="center")
    down(title_size + 4)
    header = (
        company.address,
        f"{labels['gstin']}: {company.gstin}" if company.gstin else "",
        f"{labels['phone']}: {company.phone}" if company.phone else "",
    )
    for line in header:
        if line:
            for part in str(line).splitlines()[:3]:
                text(centre, part[:70], align="center", font_size=size - 1)
                down(size + 2)
    down(4)
    rule()
    down(title_size - 4)  # room for tall Devanagari ascenders under the rule
    text(centre, labels["title"], bold=True, font_size=title_size, align="center")
    down(title_size + 6)

    text(margin, f"{labels['no']}: {receipt.number or receipt.pk}", bold=True)
    text(right, f"{labels['date']}: {receipt.receipt_date.isoformat()}", align="right")
    down()
    text(margin, f"{labels['from']}: {receipt.customer.name}"[:60])
    down()
    rule()

    for label, value in _payment_detail(receipt, labels):
        need(size + 5)
        text(margin, f"{label}:")
        text(right, str(value)[:40], align="right")
        down()
    down(2)
    rule()

    need(40)
    text(margin, labels["amount"], bold=True, font_size=size + 1)
    text(right, f"{money} {format_money(receipt.amount)}", bold=True, font_size=size + 1, align="right")
    down(size + 7)
    words = amount_in_words_hi(receipt.amount) if hindi else amount_in_words(receipt.amount)
    for line in wrap(words, right - margin, font_size=size - 1):
        need(size + 5)
        text(margin, line, font_size=size - 1)
        down(size + 1)
    down(2)
    if receipt.tds_deducted:
        section = f" ({receipt.tds_section})" if receipt.tds_section else ""
        text(margin, f"{labels['tds']}{section}:")
        text(right, f"{money} {format_money(receipt.tds_deducted)}", align="right")
        down()
    if receipt.settlement_discount:
        label = labels["discount_pending"] if discount_pending else labels["discount"]
        text(margin, f"{label}:")
        text(right, f"{money} {format_money(receipt.settlement_discount)}", align="right")
        down()
    rule()

    if allocation_rows:
        text(margin, labels["applied"], bold=True)
        down()
        for number, amount in allocation_rows:
            need(size + 5)
            text(margin + 6, f"{labels['invoice']} {number}"[:40])
            text(right, f"{money} {format_money(amount)}", align="right")
            down()
    if refund_rows:
        need(size + 5)
        text(margin, labels["refunds"], bold=True)
        down()
        for number, on, amount in refund_rows:
            need(size + 5)
            text(margin + 6, f"{labels['refund']} {number} ({on.isoformat()})"[:44])
            text(right, f"{money} {format_money(amount)}", align="right")
            down()
    if advance > 0:
        need(size + 5)
        text(margin, labels["advance"], bold=True)
        text(right, f"{money} {format_money(advance)}", bold=True, align="right")
        down()
        # A services company that pays GST on advances shows the tax inside this one: with tax it
        # is a GST receipt voucher, without it a plain acknowledgement of money received.
        if getattr(company, "advance_gst_treatment", "none") == "services" and not voided:
            from reporting.gst_returns import _advance_rate, _advance_tax_split

            rate = _advance_rate(company, receipt)
            if rate is not None:
                split = _advance_tax_split(company, receipt, advance, rate)
                text(margin, f"{labels['gst_advance']} ({split['rate']}%)")
                down()
                for label, value in (
                    (labels["taxable"], split["taxable_value"]),
                    ("CGST", split["cgst"]),
                    ("SGST", split["sgst"]),
                    ("IGST", split["igst"]),
                ):
                    if label in ("CGST", "SGST", "IGST") and Decimal(value) == 0:
                        continue
                    need(size + 5)
                    text(margin + 6, label)
                    text(right, f"{money} {format_money(Decimal(value))}", align="right")
                    down()
    rule()

    if voided:
        pdf.saveState()
        pdf.setFillGray(0.78)
        pdf.translate(centre, page_h / 2)
        pdf.rotate(35)
        stamp = 30 if thermal else 56
        if hindi:
            hi_bold.draw(pdf, labels["voided"], -hi_bold.width(labels["voided"], stamp) / 2, 0, stamp)
        else:
            pdf.setFont("Helvetica-Bold", stamp)
            pdf.drawCentredString(0, 0, labels["voided"])
        pdf.restoreState()
        reason = (receipt.void_reason or "").strip()
        if reason:
            text(margin, f"{labels['void_reason']}: {reason}"[:80], font_size=size - 1)
            down()

    if not thermal:
        need(60)
        down(30)
        text(right, labels["signatory"], align="right", font_size=size - 1)
        down()
    else:
        down(4)
        text(centre, labels["thanks"], align="center", font_size=size - 1)

    pdf.save()
    return buf.getvalue()
