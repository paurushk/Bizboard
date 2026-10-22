"""WP-BL2: PDF of Bizboard's own GST invoice or credit note to a tenant (A4, one service line).

The seller block comes from settings (``PLATFORM_LEGAL_NAME``, ``PLATFORM_ADDRESS``,
``PLATFORM_GSTIN``, ``PLATFORM_STATE``); the buyer block and amounts come from the stored row, so a
reprint always matches what was issued even after the company edits its profile.
"""

from __future__ import annotations

import io

from django.conf import settings
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sales.pdf.helpers import amount_in_words, format_money, pdf_esc
from sales.pdf.styles import GREY_HEADER, LINE, build_styles

from .models import PlatformGstInvoice


def render_platform_invoice_pdf(row: PlatformGstInvoice) -> bytes:
    styles = build_styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title=row.number, author="Bizboard",
    )
    is_credit = row.kind == PlatformGstInvoice.Kind.CREDIT_NOTE
    seller_name = getattr(settings, "PLATFORM_LEGAL_NAME", "") or "Bizboard"
    seller_address = getattr(settings, "PLATFORM_ADDRESS", "") or ""
    seller_gstin = row.platform_gstin or ""
    seller_state = getattr(settings, "PLATFORM_STATE", "") or ""
    issued = timezone.localtime(row.created_at).strftime("%d %b %Y")

    story = [
        Paragraph(pdf_esc(seller_name), styles["company_name"]),
        Paragraph(pdf_esc(seller_address).replace("\n", "<br/>"), styles["meta"]) if seller_address else Spacer(1, 1),
        Paragraph(
            f"GSTIN: {pdf_esc(seller_gstin) or 'not registered'}"
            + (f" · State: {pdf_esc(seller_state)}" if seller_state else ""),
            styles["meta"],
        ),
        Spacer(1, 4 * mm),
        Paragraph("CREDIT NOTE" if is_credit else "TAX INVOICE", styles["title"]),
        Spacer(1, 2 * mm),
    ]
    meta = [
        [Paragraph(f"<b>{'Credit note' if is_credit else 'Invoice'} no.</b> {pdf_esc(row.number)}", styles["body"]),
         Paragraph(f"<b>Date:</b> {issued}", styles["body"])],
        [Paragraph(f"<b>Place of supply:</b> {pdf_esc(row.place_of_supply) or '—'}", styles["body"]),
         Paragraph(f"<b>Financial year:</b> {pdf_esc(row.financial_year)}", styles["body"])],
    ]
    if is_credit and row.original_id:
        meta.append([
            Paragraph(f"<b>Against invoice:</b> {pdf_esc(row.original.number)}", styles["body"]),
            Paragraph(
                f"<b>Invoice date:</b> {timezone.localtime(row.original.created_at).strftime('%d %b %Y')}",
                styles["body"],
            ),
        ])
    story.append(Table(meta, colWidths=[90 * mm, 90 * mm]))
    story.append(Spacer(1, 4 * mm))
    buyer = [Paragraph("<b>Billed to</b>", styles["section_head"]),
             Paragraph(f"<b>{pdf_esc(row.buyer_legal_name) or '—'}</b>", styles["body"])]
    if row.buyer_gstin:
        buyer.append(Paragraph(f"GSTIN: {pdf_esc(row.buyer_gstin)}", styles["body_small"]))
    if row.buyer_state:
        buyer.append(Paragraph(f"State: {pdf_esc(row.buyer_state)}", styles["body_small"]))
    story.append(Table([[b] for b in buyer], colWidths=[180 * mm]))
    story.append(Spacer(1, 4 * mm))

    head = ["Description", "SAC", "Taxable value", "CGST", "SGST", "IGST", "Total"]
    line = [
        "Bizboard subscription" + (" — refund" if is_credit else ""),
        row.sac_code,
        format_money(row.taxable_amount),
        format_money(row.cgst),
        format_money(row.sgst),
        format_money(row.igst),
        format_money(row.total),
    ]
    table = Table(
        [[Paragraph(f"<b>{h}</b>", styles["th"]) for h in head],
         [Paragraph(pdf_esc(v), styles["td"] if i < 2 else styles["td_right"]) for i, v in enumerate(line)]],
        colWidths=[52 * mm, 16 * mm, 26 * mm, 20 * mm, 20 * mm, 20 * mm, 26 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREY_HEADER),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(table)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Total:</b> {format_money(row.total)}", styles["grand"]))
    story.append(Paragraph(f"Amount in words: {pdf_esc(amount_in_words(row.total))}", styles["words"]))
    if row.irn:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(f"IRN: {pdf_esc(row.irn)} · Ack {pdf_esc(row.ack_no)}", styles["body_small"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Tax is not payable on reverse charge. Paid online; this is a computer-generated document and "
        "needs no signature.",
        styles["terms"],
    ))
    doc.build(story)
    return buf.getvalue()
