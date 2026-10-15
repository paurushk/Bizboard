"""Supplier ledger statement as a PDF (A4)."""

from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sales.pdf.helpers import format_money, pdf_esc


def _label(entry_type: str) -> str:
    return str(entry_type or "").replace("_", " ").title()


def render_supplier_ledger(company, supplier, entries, *, opening, outstanding, date_from=None, date_to=None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Supplier ledger {supplier.name}", author=company.name,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"<b>{pdf_esc(company.name)}</b>", styles["Title"]),
        Paragraph(f"Supplier ledger: <b>{pdf_esc(supplier.name)}</b>", styles["Heading3"]),
    ]
    if date_from or date_to:
        story.append(Paragraph(f"Period: {date_from or 'start'} to {date_to or 'today'}", styles["Normal"]))
    story.append(Spacer(1, 4 * mm))
    rows = [["Date", "Type", "Number", "Debit", "Credit", "Balance"]]
    if opening is not None:
        rows.append(["", "Opening balance", "", "", "", format_money(opening)])
    for entry in entries:
        rows.append([
            str(entry.get("date") or ""),
            _label(entry.get("type")),
            str(entry.get("number") or ""),
            format_money(entry.get("debit")),
            format_money(entry.get("credit")),
            format_money(entry.get("balance")),
        ])
    table = Table(rows, repeatRows=1, colWidths=[24 * mm, 42 * mm, 36 * mm, 26 * mm, 26 * mm, 26 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>Balance you owe this supplier: {format_money(Decimal(str(outstanding or 0)))}</b>", styles["Normal"]))
    doc.build(story)
    return buffer.getvalue()
