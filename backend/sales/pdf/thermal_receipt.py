"""Compact thermal receipt PDF for 58mm and 80mm roll printers."""

from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .helpers import build_upi_qr_png, format_money, format_qty, tax_breakup_by_rate

THERMAL_WIDTHS_MM = (58, 80)
LINE = colors.Color(0.55, 0.55, 0.55)


def _page_width_mm(width_mm: int) -> int:
    return width_mm if width_mm in THERMAL_WIDTHS_MM else 80


def _thermal_styles(*, narrow: bool):
    base = getSampleStyleSheet()
    body_size = 7 if narrow else 8
    return {
        "center_bold": ParagraphStyle(
            "ThermalCenterBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10 if narrow else 11,
            leading=12 if narrow else 13,
            alignment=TA_CENTER,
        ),
        "center": ParagraphStyle(
            "ThermalCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=body_size,
            leading=body_size + 2,
            alignment=TA_CENTER,
        ),
        "body": ParagraphStyle(
            "ThermalBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=body_size,
            leading=body_size + 2,
            alignment=TA_LEFT,
        ),
        "body_right": ParagraphStyle(
            "ThermalBodyRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=body_size,
            leading=body_size + 2,
            alignment=TA_RIGHT,
        ),
        "bold": ParagraphStyle(
            "ThermalBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=body_size,
            leading=body_size + 2,
            alignment=TA_LEFT,
        ),
        "grand": ParagraphStyle(
            "ThermalGrand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9 if narrow else 10,
            leading=11 if narrow else 12,
            alignment=TA_RIGHT,
        ),
        "divider": ParagraphStyle(
            "ThermalDivider",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=body_size,
            leading=body_size + 2,
            alignment=TA_CENTER,
            textColor=LINE,
        ),
    }


def _invoice_datetime(invoice) -> str:
    if getattr(invoice, "completed_at", None):
        return invoice.completed_at.strftime("%d/%m/%Y %H:%M")
    return invoice.invoice_date.strftime("%d/%m/%Y")


def render_thermal_receipt(invoice, *, width_mm: int = 80) -> bytes:
    """Render a narrow thermal receipt PDF. `width_mm` is 58 or 80 (default 80)."""
    width_mm = _page_width_mm(width_mm)
    page_width = width_mm * mm
    margin = 2 * mm
    content_width = page_width - 2 * margin
    narrow = width_mm == 58
    styles = _thermal_styles(narrow=narrow)

    company = invoice.company
    customer = invoice.customer
    items = list(invoice.items.select_related("product", "product__unit").all())
    show_tax = invoice.invoice_type != invoice.InvoiceType.NON_GST

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(page_width, 800 * mm),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=3 * mm,
        bottomMargin=3 * mm,
        title=f"Receipt {invoice.number or invoice.pk}",
        author=company.name,
    )

    story = []
    story.append(Paragraph(company.name, styles["center_bold"]))
    stamp = getattr(invoice, "company_gstin", None)
    gstin = (getattr(stamp, "gstin", None) or company.gstin or "").strip()
    if gstin:
        story.append(Paragraph(f"GSTIN: {gstin}", styles["center"]))
    if company.phone:
        story.append(Paragraph(f"Ph: {company.phone}", styles["center"]))
    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph("—" * (24 if narrow else 32), styles["divider"]))
    story.append(Spacer(1, 1 * mm))

    story.append(Paragraph(f"Invoice: {invoice.number or '—'}", styles["body"]))
    story.append(Paragraph(f"Date: {_invoice_datetime(invoice)}", styles["body"]))
    if customer.name:
        story.append(Paragraph(f"Customer: {customer.name}", styles["body"]))
    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph("—" * (24 if narrow else 32), styles["divider"]))
    story.append(Spacer(1, 1 * mm))

    qty_col = 10 * mm if narrow else 12 * mm
    amt_col = 14 * mm if narrow else 16 * mm
    name_col = content_width - qty_col - amt_col

    line_rows = [[
        Paragraph("Item", styles["bold"]),
        Paragraph("Qty", styles["bold"]),
        Paragraph("Amt", styles["bold"]),
    ]]
    for item in items:
        name = item.description or item.product.name
        unit = (item.unit_name or "PCS").upper()
        qty_label = f"{format_qty(item.quantity)} {unit}"
        line_rows.append([
            Paragraph(name, styles["body"]),
            Paragraph(qty_label, styles["body_right"]),
            Paragraph(format_money(item.line_total), styles["body_right"]),
        ])
        if show_tax and Decimal(item.gst_rate or 0) > 0:
            line_tax = (
                Decimal(item.cgst or 0)
                + Decimal(item.sgst or 0)
                + Decimal(item.igst or 0)
                + Decimal(getattr(item, "cess", 0) or 0)
            )
            rate_label = format_money(item.gst_rate).rstrip("0").rstrip(".")
            line_rows.append([
                Paragraph(
                    f"  @{format_money(item.unit_price)} +{rate_label}% tax {format_money(line_tax)}",
                    styles["body"],
                ),
                "",
                "",
            ])

    items_table = Table(line_rows, colWidths=[name_col, qty_col, amt_col])
    items_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LINEBELOW", (0, 0), (-1, 0), 0.3, LINE),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("—" * (24 if narrow else 32), styles["divider"]))
    story.append(Spacer(1, 1 * mm))

    summary_rows = []
    if show_tax:
        summary_rows.append([
            Paragraph("Taxable", styles["body"]),
            Paragraph(format_money(invoice.taxable_total), styles["body_right"]),
        ])
        for row in tax_breakup_by_rate(items, tax_enabled=True):
            summary_rows.append([
                Paragraph(row["label"], styles["body"]),
                Paragraph(format_money(row["amount"]), styles["body_right"]),
            ])
    additional_charges = Decimal(getattr(invoice, "additional_charges", 0) or 0)
    if additional_charges:
        summary_rows.append([
            Paragraph("Add. charges", styles["body"]),
            Paragraph(format_money(additional_charges), styles["body_right"]),
        ])
    invoice_discount = Decimal(getattr(invoice, "invoice_discount", 0) or 0)
    if invoice_discount:
        summary_rows.append([
            Paragraph("Discount", styles["body"]),
            Paragraph(format_money(invoice_discount), styles["body_right"]),
        ])
    tcs_amount = Decimal(getattr(invoice, "tcs_amount", 0) or 0)
    if tcs_amount:
        summary_rows.append([
            Paragraph("TCS", styles["body"]),
            Paragraph(format_money(tcs_amount), styles["body_right"]),
        ])
    if invoice.round_off and Decimal(invoice.round_off) != 0:
        summary_rows.append([
            Paragraph("Round off", styles["body"]),
            Paragraph(format_money(invoice.round_off), styles["body_right"]),
        ])

    label_col = content_width * 0.55
    value_col = content_width * 0.45
    if summary_rows:
        summary_table = Table(summary_rows, colWidths=[label_col, value_col])
        summary_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 1 * mm))

    total_table = Table(
        [[Paragraph("TOTAL", styles["grand"]), Paragraph(format_money(invoice.grand_total), styles["grand"])]],
        colWidths=[label_col, value_col],
    )
    total_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(total_table)

    if company.upi_id:
        story.append(Spacer(1, 2 * mm))
        qr_size = 22 * mm if narrow else 26 * mm
        qr_png = build_upi_qr_png(
            company.upi_id,
            amount=invoice.grand_total,
            note=f"Invoice {invoice.number or invoice.pk}",
        )
        if qr_png:
            qr_img = Image(io.BytesIO(qr_png), width=qr_size, height=qr_size)
            qr_img.hAlign = "CENTER"
            story.append(qr_img)
            story.append(Spacer(1, 1 * mm))
        story.append(Paragraph(f"UPI: {company.upi_id}", styles["center"]))

    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Thank you!", styles["center"]))
    story.append(Spacer(1, 3 * mm))

    doc.build(story)
    return buffer.getvalue()
