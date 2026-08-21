"""Vyapar/Mittal-style GST TAX INVOICE renderer (A4)."""

from __future__ import annotations

import io
from decimal import Decimal

from django.db.models import Sum
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ledgers.services import LedgerService
from payments.models import PaymentAllocation

from .helpers import (
    amount_in_words,
    build_upi_qr_png,
    format_money,
    format_qty,
    tax_breakup_by_rate,
)
from .styles import (
    COL_WIDTHS_SIMPLE,
    COL_WIDTHS_TAX,
    GREY_HEADER,
    GREY_TOTAL,
    LINE,
    build_styles,
)

DEFAULT_TERMS = (
    "1. Goods once sold will not be taken back or exchanged.\n"
    "2. All disputes are subject to the seller's city jurisdiction only."
)


def _is_sandbox_gsp(company) -> bool:
    provider = (getattr(company, "gsp_provider", None) or "").strip().lower()
    return not provider or provider == "sandbox"


def _manual_irn_watermark(canvas, _doc):
    """BB-000214: mark PDFs when IRN was client-attested, not GSP-verified."""
    canvas.saveState()
    canvas.setFillGray(0.82)
    canvas.setFont("Helvetica-Bold", 48)
    canvas.translate(A4[0] / 2, A4[1] / 2)
    canvas.rotate(40)
    canvas.drawCentredString(0, 0, "MANUAL IRN")
    canvas.restoreState()


def _company_address(company) -> str:
    parts = [
        company.address or "",
        ", ".join(p for p in [company.city, company.state, company.pincode] if p),
    ]
    return "\n".join(p for p in parts if p).strip()


def _party_block(styles, title: str, name: str, address: str, gstin: str, phone: str) -> Table:
    lines = [Paragraph(f"<b>{title}</b>", styles["section_head"])]
    lines.append(Paragraph(name or "—", styles["body"]))
    if address:
        for part in address.split("\n"):
            if part.strip():
                lines.append(Paragraph(part.strip(), styles["body_small"]))
    if gstin:
        lines.append(Paragraph(f"GSTIN: {gstin}", styles["body_small"]))
    if phone:
        lines.append(Paragraph(f"Ph: {phone}", styles["body_small"]))
    inner = Table([[lines]], colWidths=[85 * mm])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREY_HEADER),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return inner


def render_gst_tax_invoice(invoice, *, copy: str = "ORIGINAL") -> bytes:
    """Render a complete GST Tax Invoice PDF. `copy` is ORIGINAL or DUPLICATE."""
    copy = (copy or "ORIGINAL").upper()
    if copy not in ("ORIGINAL", "DUPLICATE"):
        copy = "ORIGINAL"

    company = invoice.company
    customer = invoice.customer
    items = list(invoice.items.select_related("product", "product__unit").all())
    styles = build_styles()
    show_tax = invoice.invoice_type != invoice.InvoiceType.NON_GST

    allocated = (
        PaymentAllocation.objects.filter(sales_invoice=invoice, reversed_at__isnull=True).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    # Prefer ledger outstanding math for balance (accounts for returns).
    try:
        balance = LedgerService.sales_invoice_outstanding(invoice)
        received = max(invoice.grand_total - balance, Decimal("0"))
    except Exception:
        received = allocated
        balance = max(invoice.grand_total - received, Decimal("0"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Invoice {invoice.number or invoice.pk}",
        author=company.name,
    )

    story = []

    # ---- Header ----
    seller_bits = []
    logo_asset = getattr(company, "logo", None)
    if logo_asset and getattr(logo_asset, "file", None):
        try:
            logo_img = Image(logo_asset.file.path if hasattr(logo_asset.file, "path") else logo_asset.file, width=28 * mm, height=28 * mm)
            logo_img.hAlign = "LEFT"
            seller_bits.append(logo_img)
            seller_bits.append(Spacer(1, 1 * mm))
        except Exception:
            pass
    seller_bits.append(Paragraph(company.name, styles["company_name"]))
    if company.gstin:
        seller_bits.append(Paragraph(f"GSTIN: {company.gstin}", styles["meta"]))
    if company.phone:
        seller_bits.append(Paragraph(f"Mobile: {company.phone}", styles["meta"]))
    addr = _company_address(company)
    if addr:
        for line in addr.split("\n"):
            seller_bits.append(Paragraph(line, styles["meta"]))

    title_label = "TAX INVOICE" if show_tax else invoice.get_invoice_type_display().upper()
    stamp = Table([[Paragraph(copy, styles["copy_stamp"])]], colWidths=[28 * mm])
    stamp.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    right_col = [
        Paragraph(title_label, styles["title"]),
        Spacer(1, 2 * mm),
        stamp,
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Invoice No.</b> {invoice.number or '—'}", styles["meta"]),
        Paragraph(
            f"<b>Invoice Date</b> {invoice.invoice_date.strftime('%d/%m/%Y')}",
            styles["meta"],
        ),
    ]
    if getattr(invoice, "due_date", None):
        right_col.append(
            Paragraph(
                f"<b>Due Date</b> {invoice.due_date.strftime('%d/%m/%Y')}",
                styles["meta"],
            )
        )

    header = Table(
        [[seller_bits, right_col]],
        colWidths=[110 * mm, 76 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 4 * mm))

    # ---- Bill To / Ship To ----
    bill_addr = customer.billing_address or ""
    ship_addr = customer.shipping_address or customer.billing_address or ""
    parties = Table(
        [[
            _party_block(
                styles, "BILL TO", customer.name, bill_addr,
                customer.gstin or "", customer.phone or "",
            ),
            _party_block(
                styles, "SHIP TO", customer.name, ship_addr,
                customer.gstin or "", customer.phone or "",
            ),
        ]],
        colWidths=[93 * mm, 93 * mm],
    )
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 3),
        ("LEFTPADDING", (1, 0), (1, 0), 3),
    ]))
    story.append(parties)
    story.append(Spacer(1, 4 * mm))

    # ---- Line items ----
    if show_tax:
        data = [[
            Paragraph("S.NO.", styles["th"]),
            Paragraph("ITEMS", styles["th"]),
            Paragraph("HSN", styles["th"]),
            Paragraph("QTY.", styles["th"]),
            Paragraph("MRP", styles["th"]),
            Paragraph("RATE", styles["th"]),
            Paragraph("TAX", styles["th"]),
            Paragraph("AMOUNT", styles["th"]),
        ]]
        total_qty = Decimal("0")
        total_tax = Decimal("0")
        total_amount = Decimal("0")
        for idx, item in enumerate(items, start=1):
            total_qty += Decimal(item.quantity)
            line_tax = Decimal(item.cgst or 0) + Decimal(item.sgst or 0) + Decimal(item.igst or 0)
            total_tax += line_tax
            total_amount += Decimal(item.line_total or 0)
            unit = (item.unit_name or "PCS").upper()
            item_cell = [
                Paragraph(item.description or item.product.name, styles["td"]),
            ]
            # Subtle second line with product name if description differs
            if item.description and item.description != item.product.name:
                item_cell.append(Paragraph(item.product.name, styles["body_small"]))
            data.append([
                Paragraph(str(idx), styles["td_center"]),
                item_cell,
                Paragraph(item.hsn_code or item.product.hsn_code or "—", styles["td_center"]),
                Paragraph(f"{format_qty(item.quantity)} {unit}", styles["td_center"]),
                Paragraph(format_money(item.mrp), styles["td_right"]),
                Paragraph(format_money(item.unit_price), styles["td_right"]),
                [
                    Paragraph(format_money(line_tax), styles["td_right"]),
                    Paragraph(f"({format_money(item.gst_rate).rstrip('0').rstrip('.')}%)", styles["body_small"]),
                ],
                Paragraph(format_money(item.line_total), styles["td_right"]),
            ])
        # Totals row
        data.append([
            "",
            Paragraph("<b>TOTAL</b>", styles["td"]),
            "",
            Paragraph(f"<b>{format_qty(total_qty)}</b>", styles["td_center"]),
            "",
            "",
            Paragraph(f"<b>{format_money(total_tax)}</b>", styles["td_right"]),
            Paragraph(f"<b>{format_money(total_amount)}</b>", styles["td_right"]),
        ])
        col_widths = COL_WIDTHS_TAX
    else:
        data = [[
            Paragraph("S.NO.", styles["th"]),
            Paragraph("ITEMS", styles["th"]),
            Paragraph("QTY.", styles["th"]),
            Paragraph("RATE", styles["th"]),
            Paragraph("DISC%", styles["th"]),
            Paragraph("AMOUNT", styles["th"]),
        ]]
        total_qty = Decimal("0")
        total_amount = Decimal("0")
        for idx, item in enumerate(items, start=1):
            total_qty += Decimal(item.quantity)
            total_amount += Decimal(item.line_total or 0)
            unit = (item.unit_name or "PCS").upper()
            data.append([
                Paragraph(str(idx), styles["td_center"]),
                Paragraph(item.description or item.product.name, styles["td"]),
                Paragraph(f"{format_qty(item.quantity)} {unit}", styles["td_center"]),
                Paragraph(format_money(item.unit_price), styles["td_right"]),
                Paragraph(format_money(item.discount_percent), styles["td_right"]),
                Paragraph(format_money(item.line_total), styles["td_right"]),
            ])
        data.append([
            "",
            Paragraph("<b>TOTAL</b>", styles["td"]),
            Paragraph(f"<b>{format_qty(total_qty)}</b>", styles["td_center"]),
            "",
            "",
            Paragraph(f"<b>{format_money(total_amount)}</b>", styles["td_right"]),
        ])
        col_widths = COL_WIDTHS_SIMPLE

    items_table = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), GREY_HEADER),
        ("BACKGROUND", (0, -1), (-1, -1), GREY_TOTAL),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    items_table.setStyle(TableStyle(style_cmds))
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # ---- Footer: QR + tax summary ----
    left_flow = []
    # e-Invoice signed QR (when IRN generated) takes precedence over UPI QR.
    einvoice_qr = (getattr(invoice, "einvoice_qr", None) or "").strip()
    sandbox_gsp = _is_sandbox_gsp(company)
    einvoice_status = getattr(invoice, "einvoice_status", None)
    show_einvoice_qr = einvoice_status in ("GENERATED", "MANUAL_IRN") and einvoice_qr
    if show_einvoice_qr:
        try:
            import qrcode

            qr = qrcode.QRCode(version=None, box_size=3, border=1)
            qr.add_data(einvoice_qr)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            left_flow.append(Image(io.BytesIO(buf.getvalue()), width=32 * mm, height=32 * mm))
            qr_label = "<b>e-Invoice QR</b>"
            if einvoice_status == "MANUAL_IRN":
                qr_label += " <b>(MANUAL IRN)</b>"
            elif sandbox_gsp:
                qr_label += " <b>(SANDBOX)</b>"
            left_flow.append(Paragraph(qr_label, styles["meta"]))
            if getattr(invoice, "irn", None):
                irn_text = f"IRN: {invoice.irn[:24]}…"
                if einvoice_status == "MANUAL_IRN":
                    irn_text += " (MANUAL)"
                elif sandbox_gsp:
                    irn_text += " (SANDBOX)"
                left_flow.append(Paragraph(irn_text, styles["meta"]))
        except Exception:
            left_flow.append(Paragraph("<b>e-Invoice QR unavailable</b>", styles["meta"]))
    include_qr = getattr(invoice, "include_payment_qr", True)
    if include_qr and not show_einvoice_qr:
        # Amount-lock QR to outstanding when partially paid (Phase 3 gap).
        from ledgers.services import LedgerService

        try:
            qr_amount = LedgerService.sales_invoice_outstanding(invoice)
        except Exception:
            qr_amount = invoice.grand_total
        if qr_amount is None or qr_amount < 0:
            qr_amount = invoice.grand_total
        qr_png = build_upi_qr_png(
            company.upi_id,
            amount=qr_amount if qr_amount > 0 else invoice.grand_total,
            note=f"Invoice {invoice.number or invoice.pk}",
        )
        if qr_png:
            qr_img = Image(io.BytesIO(qr_png), width=28 * mm, height=28 * mm)
            left_flow.append(qr_img)
            left_flow.append(Spacer(1, 1 * mm))
            left_flow.append(Paragraph(f"<b>UPI ID:</b> {company.upi_id}", styles["meta"]))
        elif company.upi_id:
            left_flow.append(Paragraph(f"<b>UPI ID:</b> {company.upi_id}", styles["meta"]))

    if getattr(invoice, "include_bank_details", False) and (
        company.bank_name or company.bank_account
    ):
        left_flow.append(Spacer(1, 2 * mm))
        left_flow.append(Paragraph("<b>Bank Details</b>", styles["section_head"]))
        if company.bank_name:
            left_flow.append(Paragraph(company.bank_name, styles["meta"]))
        if company.bank_account:
            left_flow.append(Paragraph(f"A/C: {company.bank_account}", styles["meta"]))
        if company.bank_ifsc:
            left_flow.append(Paragraph(f"IFSC: {company.bank_ifsc}", styles["meta"]))

    include_terms = getattr(invoice, "include_terms", True)
    if include_terms:
        terms = (
            (getattr(invoice, "terms_text", None) or "").strip()
            or (company.invoice_terms or "").strip()
            or DEFAULT_TERMS
        )
        left_flow.append(Spacer(1, 3 * mm))
        left_flow.append(Paragraph("<b>Terms and Conditions</b>", styles["section_head"]))
        for line in terms.split("\n"):
            if line.strip():
                left_flow.append(Paragraph(line.strip(), styles["terms"]))

    right_rows = []
    additional_charges = Decimal(getattr(invoice, "additional_charges", 0) or 0)
    invoice_discount = Decimal(getattr(invoice, "invoice_discount", 0) or 0)
    if additional_charges:
        right_rows.append([
            Paragraph("Additional Charges (non-taxable)", styles["total_label"]),
            Paragraph(format_money(additional_charges), styles["total_value"]),
        ])
    if show_tax:
        right_rows.append([
            Paragraph("TAXABLE AMOUNT", styles["total_label"]),
            Paragraph(format_money(invoice.taxable_total), styles["total_value"]),
        ])
        for row in tax_breakup_by_rate(items, tax_enabled=True):
            right_rows.append([
                Paragraph(row["label"], styles["total_label"]),
                Paragraph(format_money(row["amount"]), styles["total_value"]),
            ])
    discount_mode = getattr(invoice, "invoice_discount_mode", "AFTER_TAX")
    if invoice_discount and discount_mode == "BEFORE_TAX":
        # BUG-204: the discount has already been netted into TAXABLE AMOUNT
        # and the tax rows above — printing it again as a further deduction
        # would make the visible arithmetic not sum to TOTAL.
        right_rows.append([
            Paragraph("Discount (already reflected above)", styles["total_label"]),
            Paragraph(format_money(invoice_discount), styles["total_value"]),
        ])
    elif invoice_discount:
        right_rows.append([
            Paragraph("Discount", styles["total_label"]),
            Paragraph(format_money(invoice_discount), styles["total_value"]),
        ])
    if invoice.round_off and Decimal(invoice.round_off) != 0:
        right_rows.append([
            Paragraph("Round Off", styles["total_label"]),
            Paragraph(format_money(invoice.round_off), styles["total_value"]),
        ])
    right_rows.append([
        Paragraph("TOTAL", styles["grand"]),
        Paragraph(format_money(invoice.grand_total), styles["grand"]),
    ])
    right_rows.append([
        Paragraph("Received Amount", styles["total_label"]),
        Paragraph(format_money(received), styles["total_value"]),
    ])
    right_rows.append([
        Paragraph("Balance", styles["total_label"]),
        Paragraph(format_money(balance), styles["total_value"]),
    ])

    totals_tbl = Table(right_rows, colWidths=[40 * mm, 28 * mm])
    totals_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, -3), (-1, -3), GREY_TOTAL),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("LINEBELOW", (0, 0), (-1, -4), 0.2, LINE),
    ]))

    footer_top = Table(
        [[left_flow, totals_tbl]],
        colWidths=[110 * mm, 76 * mm],
    )
    footer_top.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([footer_top]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"<b>Invoice Amount In Words:</b> {amount_in_words(invoice.grand_total)}",
        styles["words"],
    ))
    story.append(Spacer(1, 8 * mm))

    sign_flow = [
        Paragraph(f"For {company.name}", styles["td_right"]),
        Spacer(1, 4 * mm),
    ]
    sig = getattr(invoice, "signature", None) or getattr(company, "signature", None)
    if sig and getattr(sig, "file", None):
        try:
            sig_img = Image(
                sig.file.path if hasattr(sig.file, "path") else sig.file,
                width=35 * mm,
                height=18 * mm,
            )
            sig_img.hAlign = "RIGHT"
            sign_flow.append(sig_img)
            sign_flow.append(Spacer(1, 1 * mm))
        except Exception:
            pass
    sign_flow.append(Paragraph("<b>Authorized Signatory</b>", styles["td_right"]))
    sign = Table(
        [[Paragraph("", styles["body"]), sign_flow]],
        colWidths=[100 * mm, 86 * mm],
    )
    story.append(sign)

    if einvoice_status == "MANUAL_IRN":
        doc.build(story, onFirstPage=_manual_irn_watermark, onLaterPages=_manual_irn_watermark)
    else:
        doc.build(story)
    return buffer.getvalue()
