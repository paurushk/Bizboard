"""Tax Credit/Debit Note and Delivery Challan A4 PDF renderers."""

from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .helpers import amount_in_words, format_money, format_qty, pdf_esc, tax_breakup_by_rate
from .styles import GREY_HEADER, GREY_TOTAL, LINE, build_styles


def _invoice_reference(invoice) -> str:
    number = invoice.number or str(invoice.pk)
    inv_date = getattr(invoice, "invoice_date", None)
    if inv_date:
        return f"{number} dated {inv_date}"
    return number


def _addr(party) -> str:
    parts = [
        getattr(party, "billing_address", None) or getattr(party, "address", "") or "",
        ", ".join(
            p
            for p in [
                getattr(party, "city", "") or "",
                getattr(party, "state", "") or "",
                getattr(party, "pincode", "") or "",
            ]
            if p
        ),
    ]
    return "<br/>".join(p for p in parts if p)


def _render_note_like(
    *,
    company,
    customer,
    number: str,
    doc_date,
    title: str,
    items,
    totals,
    reference_label: str = "",
    reference_value: str = "",
    reason: str = "",
    notes: str = "",
    tax_enabled: bool = True,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = build_styles()
    story = []

    story.append(Paragraph(pdf_esc(company.name or "Business"), styles["company_name"]))
    story.append(Paragraph(title, styles["title"]))
    meta = [
        f"<b>Number:</b> {pdf_esc(number or '—')}",
        f"<b>Date:</b> {pdf_esc(doc_date)}",
    ]
    if reference_label and reference_value:
        meta.append(f"<b>{pdf_esc(reference_label)}:</b> {pdf_esc(reference_value)}")
    if reason:
        meta.append(f"<b>Reason:</b> {pdf_esc(reason)}")
    story.append(Paragraph("<br/>".join(meta), styles["meta"]))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("<b>Bill To</b>", styles["section_head"]))
    story.append(Paragraph(pdf_esc(customer.name or ""), styles["body"]))
    if getattr(customer, "gstin", None):
        story.append(Paragraph(f"GSTIN: {pdf_esc(customer.gstin)}", styles["body"]))
    addr = _addr(customer)
    if addr:
        story.append(Paragraph(pdf_esc(addr), styles["body_small"]))
    story.append(Spacer(1, 4 * mm))

    header = ["#", "Item", "HSN", "Qty", "Rate", "Taxable", "Tax", "Total"]
    rows = [header]
    for idx, item in enumerate(items, start=1):
        tax = (item.cgst or 0) + (item.sgst or 0) + (item.igst or 0)
        rows.append([
            str(idx),
            item.description or getattr(item.product, "name", ""),
            getattr(item, "hsn_code", "") or getattr(item.product, "hsn_code", "") or "",
            format_qty(item.quantity),
            format_money(item.unit_price),
            format_money(item.taxable_amount),
            format_money(tax),
            format_money(item.line_total),
        ])
    table = Table(rows, colWidths=[12 * mm, 55 * mm, 18 * mm, 16 * mm, 20 * mm, 22 * mm, 18 * mm, 22 * mm])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREY_HEADER),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    story.append(table)
    story.append(Spacer(1, 3 * mm))

    summary = [
        ["Taxable", format_money(totals["taxable"])],
        ["CGST", format_money(totals["cgst"])],
        ["SGST", format_money(totals["sgst"])],
        ["IGST", format_money(totals["igst"])],
        ["Cess", format_money(totals.get("cess") or 0)],
        ["Additional charges", format_money(totals.get("charges") or 0)],
        ["TCS", format_money(totals.get("tcs") or 0)],
        ["Round off", format_money(totals["round_off"])],
        ["Grand Total", format_money(totals["grand"])],
    ]
    sum_table = Table(summary, colWidths=[40 * mm, 30 * mm])
    sum_table.setStyle(
        TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("BACKGROUND", (0, -1), (-1, -1), GREY_TOTAL),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
        ])
    )
    story.append(sum_table)
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            f"<b>Amount in words:</b> {amount_in_words(totals['grand'])}",
            styles["body"],
        )
    )
    if tax_enabled:
        breakup = tax_breakup_by_rate(items, tax_enabled=True)
        if breakup:
            story.append(
                Paragraph(
                    " · ".join(f"{b['label']}: {format_money(b['amount'])}" for b in breakup),
                    styles["body"],
                )
            )
    if notes:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>Notes:</b> {pdf_esc(notes)}", styles["body"]))

    doc.build(story)
    return buf.getvalue()


def render_credit_note(note) -> bytes:
    reason = note.get_reason_display() if hasattr(note, "get_reason_display") else note.reason
    if note.reason_detail:
        reason = f"{reason} — {note.reason_detail}"
    items = list(note.items.select_related("product").all())
    return _render_note_like(
        company=note.company,
        customer=note.customer,
        number=note.number,
        doc_date=note.note_date,
        title="TAX CREDIT NOTE",
        items=items,
        totals={
            "taxable": note.taxable_total,
            "cgst": note.cgst_total,
            "sgst": note.sgst_total,
            "igst": note.igst_total,
            "cess": getattr(note, "cess_total", 0),
            "charges": getattr(note, "additional_charges", 0),
            "tcs": getattr(note, "tcs_amount", 0),
            "round_off": note.round_off,
            "grand": note.grand_total,
        },
        reference_label="Against Invoice",
        reference_value=_invoice_reference(note.sales_invoice),
        reason=reason,
        notes=note.notes or "",
        tax_enabled=True,
    )


def render_debit_note(note) -> bytes:
    reason = note.get_reason_display() if hasattr(note, "get_reason_display") else note.reason
    if note.reason_detail:
        reason = f"{reason} — {note.reason_detail}"
    items = list(note.items.select_related("product").all())
    return _render_note_like(
        company=note.company,
        customer=note.customer,
        number=note.number,
        doc_date=note.note_date,
        title="TAX DEBIT NOTE",
        items=items,
        totals={
            "taxable": note.taxable_total,
            "cgst": note.cgst_total,
            "sgst": note.sgst_total,
            "igst": note.igst_total,
            "cess": getattr(note, "cess_total", 0),
            "charges": getattr(note, "additional_charges", 0),
            "tcs": getattr(note, "tcs_amount", 0),
            "round_off": note.round_off,
            "grand": note.grand_total,
        },
        reference_label="Against Invoice",
        reference_value=_invoice_reference(note.sales_invoice),
        reason=reason,
        notes=note.notes or "",
        tax_enabled=True,
    )


def render_delivery_challan(challan) -> bytes:
    items = list(challan.items.select_related("product").all())
    transport = " · ".join(
        p
        for p in [
            f"Vehicle: {challan.vehicle_number}" if challan.vehicle_number else "",
            f"Transporter: {challan.transporter_name}" if challan.transporter_name else "",
        ]
        if p
    )
    notes = challan.notes or ""
    if transport:
        notes = f"{transport}\n{notes}".strip()
    return _render_note_like(
        company=challan.company,
        customer=challan.customer,
        number=challan.number,
        doc_date=challan.challan_date,
        title="DELIVERY CHALLAN",
        items=items,
        totals={
            "taxable": challan.taxable_total or Decimal("0"),
            "cgst": challan.cgst_total or Decimal("0"),
            "sgst": challan.sgst_total or Decimal("0"),
            "igst": challan.igst_total or Decimal("0"),
            "round_off": challan.round_off or Decimal("0"),
            "grand": challan.grand_total or Decimal("0"),
        },
        reference_label="Sales Order",
        reference_value=(
            challan.sales_order.number if challan.sales_order_id and challan.sales_order.number else ""
        ),
        reason="",
        notes=notes,
        tax_enabled=bool(challan.cgst_total or challan.sgst_total or challan.igst_total),
    )
