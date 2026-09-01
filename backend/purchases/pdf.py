"""GST Purchase Bill & Purchase Order PDF renderer (A4).

Compliant with statutory GST invoicing rules (Rule 46 / Rule 54 of CGST Rules 2017).
"""

from __future__ import annotations

import io
import logging
from collections import defaultdict
from decimal import Decimal

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

from sales.pdf.helpers import amount_in_words, format_money, format_qty, pdf_esc
from sales.pdf.styles import (
    GREY_HEADER,
    GREY_TOTAL,
    LINE,
    build_styles,
)

logger = logging.getLogger("bizboard.pdf")


def _company_address(company) -> str:
    parts = [
        company.address or "",
        ", ".join(p for p in [company.city, company.state, company.pincode] if p),
    ]
    return "\n".join(p for p in parts if p).strip()


def _party_block(styles, title: str, name: str, address: str, gstin: str, phone: str, state: str = "", state_code: str = "") -> Table:
    lines = [Paragraph(f"<b>{pdf_esc(title)}</b>", styles["section_head"])]
    lines.append(Paragraph(f"<b>{pdf_esc(name) or '—'}</b>", styles["body"]))
    if address:
        for part in address.split("\n"):
            if part.strip():
                lines.append(Paragraph(part.strip(), styles["body_small"]))
    if gstin:
        lines.append(Paragraph(f"<b>GSTIN:</b> {gstin}", styles["body_small"]))
    if state or state_code:
        st_text = f"<b>State:</b> {state}"
        if state_code:
            st_text += f" (Code: {state_code})"
        lines.append(Paragraph(st_text, styles["body_small"]))
    if phone:
        lines.append(Paragraph(f"<b>Ph:</b> {phone}", styles["body_small"]))
    inner = Table([[lines]], colWidths=[88 * mm])
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


def _build_hsn_summary_table(items, styles, intra_state: bool) -> Table:
    """Build statutory HSN/SAC-wise tax summary table."""
    hsn_map: dict[str, dict] = defaultdict(lambda: {
        "taxable": Decimal("0"),
        "cgst_rate": Decimal("0"),
        "cgst_amt": Decimal("0"),
        "sgst_rate": Decimal("0"),
        "sgst_amt": Decimal("0"),
        "igst_rate": Decimal("0"),
        "igst_amt": Decimal("0"),
        "cess_amt": Decimal("0"),
        "total_tax": Decimal("0"),
    })

    for item in items:
        hsn = item.hsn_code or getattr(item.product, "hsn_code", "") or "—"
        rate = Decimal(str(item.gst_rate or 0))
        taxable = Decimal(str(item.taxable_amount or item.line_total or 0))
        cgst = Decimal(str(item.cgst or 0))
        sgst = Decimal(str(item.sgst or 0))
        igst = Decimal(str(item.igst or 0))
        cess = Decimal(str(getattr(item, "cess", 0) or 0))

        entry = hsn_map[hsn]
        entry["taxable"] += taxable
        if intra_state:
            entry["cgst_rate"] = rate / 2
            entry["cgst_amt"] += cgst
            entry["sgst_rate"] = rate / 2
            entry["sgst_amt"] += sgst
        else:
            entry["igst_rate"] = rate
            entry["igst_amt"] += igst
        entry["cess_amt"] += cess
        entry["total_tax"] += (cgst + sgst + igst + cess)

    rows = []
    if intra_state:
        rows.append([
            Paragraph("HSN/SAC", styles["th"]),
            Paragraph("Taxable Value", styles["th"]),
            Paragraph("CGST Rate", styles["th"]),
            Paragraph("CGST Amount", styles["th"]),
            Paragraph("SGST Rate", styles["th"]),
            Paragraph("SGST Amount", styles["th"]),
            Paragraph("Cess", styles["th"]),
            Paragraph("Total Tax", styles["th"]),
        ])
        for hsn, d in sorted(hsn_map.items()):
            rows.append([
                Paragraph(hsn, styles["td_center"]),
                Paragraph(format_money(d["taxable"]), styles["td_right"]),
                Paragraph(f"{d['cgst_rate']}%", styles["td_center"]),
                Paragraph(format_money(d["cgst_amt"]), styles["td_right"]),
                Paragraph(f"{d['sgst_rate']}%", styles["td_center"]),
                Paragraph(format_money(d["sgst_amt"]), styles["td_right"]),
                Paragraph(format_money(d["cess_amt"]), styles["td_right"]),
                Paragraph(format_money(d["total_tax"]), styles["td_right"]),
            ])
        col_widths = [24 * mm, 28 * mm, 18 * mm, 22 * mm, 18 * mm, 22 * mm, 22 * mm, 28 * mm]
    else:
        rows.append([
            Paragraph("HSN/SAC", styles["th"]),
            Paragraph("Taxable Value", styles["th"]),
            Paragraph("IGST Rate", styles["th"]),
            Paragraph("IGST Amount", styles["th"]),
            Paragraph("Cess", styles["th"]),
            Paragraph("Total Tax", styles["th"]),
        ])
        for hsn, d in sorted(hsn_map.items()):
            rows.append([
                Paragraph(hsn, styles["td_center"]),
                Paragraph(format_money(d["taxable"]), styles["td_right"]),
                Paragraph(f"{d['igst_rate']}%", styles["td_center"]),
                Paragraph(format_money(d["igst_amt"]), styles["td_right"]),
                Paragraph(format_money(d["cess_amt"]), styles["td_right"]),
                Paragraph(format_money(d["total_tax"]), styles["td_right"]),
            ])
        col_widths = [32 * mm, 38 * mm, 24 * mm, 30 * mm, 26 * mm, 32 * mm]

    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREY_HEADER),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def render_gst_purchase_bill(invoice, *, copy: str = "ORIGINAL") -> bytes:
    """Render a statutory GST-compliant Purchase Bill / Inward Tax Invoice PDF."""
    copy = (copy or "ORIGINAL").upper()
    if copy not in ("ORIGINAL", "DUPLICATE"):
        copy = "ORIGINAL"

    from ledgers.services import LedgerService

    company = invoice.company
    supplier = invoice.supplier
    items = list(invoice.items.select_related("product", "product__unit").all())
    styles = build_styles()

    from core.services.place_of_supply import party_intra_state
    intra_state = party_intra_state(company, supplier.state, supplier.gstin or "")

    balance = LedgerService.purchase_invoice_outstanding(invoice)
    allocated = max(Decimal(str(invoice.grand_total or 0)) - Decimal(str(balance or 0)), Decimal("0"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Purchase Bill {invoice.number or invoice.pk}",
        author=company.name,
    )

    story = []

    # ---- Header (Buyer / Company Info on Left, Document Meta on Right) ----
    buyer_bits = []
    logo_asset = getattr(company, "logo", None)
    if logo_asset and getattr(logo_asset, "file", None):
        try:
            logo_img = Image(logo_asset.file.path if hasattr(logo_asset.file, "path") else logo_asset.file, width=24 * mm, height=24 * mm)
            logo_img.hAlign = "LEFT"
            buyer_bits.append(logo_img)
            buyer_bits.append(Spacer(1, 1 * mm))
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Skipping purchase PDF logo: %s", exc)
    buyer_bits.append(Paragraph(f"<b>{pdf_esc(company.name)}</b>", styles["company_name"]))
    if company.gstin:
        buyer_bits.append(Paragraph(f"<b>GSTIN:</b> {pdf_esc(company.gstin)}", styles["meta"]))
    if company.phone:
        buyer_bits.append(Paragraph(f"<b>Phone:</b> {company.phone}", styles["meta"]))
    addr = _company_address(company)
    if addr:
        for line in addr.split("\n"):
            buyer_bits.append(Paragraph(line, styles["meta"]))

    stamp = Table([[Paragraph(f"<b>{copy}</b>", styles["copy_stamp"])]], colWidths=[32 * mm])
    stamp.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    doc_details = [
        Paragraph("<b>PURCHASE BILL</b>", styles["title"]),
        Spacer(1, 1 * mm),
        stamp,
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Bill No:</b> {invoice.number or '—'}", styles["meta"]),
        Paragraph(f"<b>Bill Date:</b> {invoice.invoice_date.strftime('%d/%m/%Y')}", styles["meta"]),
    ]
    supplier_bill = (
        getattr(invoice, "supplier_bill_number", None)
        or getattr(invoice, "supplier_invoice_number", None)
        or getattr(invoice, "reference", None)
    )
    if supplier_bill:
        doc_details.append(Paragraph(f"<b>Supplier Bill No:</b> {supplier_bill}", styles["meta"]))
    if getattr(invoice, "supplier_invoice_date", None):
        doc_details.append(Paragraph(f"<b>Supplier Bill Date:</b> {invoice.supplier_invoice_date.strftime('%d/%m/%Y')}", styles["meta"]))
    if getattr(invoice, "due_date", None):
        doc_details.append(Paragraph(f"<b>Due Date:</b> {invoice.due_date.strftime('%d/%m/%Y')}", styles["meta"]))

    pos = getattr(invoice, "place_of_supply", None) or supplier.state or company.state or "—"
    doc_details.append(Paragraph(f"<b>Place of Supply:</b> {pos}", styles["meta"]))
    rcm_text = "YES" if getattr(invoice, "is_reverse_charge", False) else "NO"
    doc_details.append(Paragraph(f"<b>Reverse Charge (RCM):</b> {rcm_text}", styles["meta"]))
    if hasattr(invoice, "itc_eligibility"):
        doc_details.append(Paragraph(f"<b>ITC Eligibility:</b> {invoice.get_itc_eligibility_display()}", styles["meta"]))

    header = Table([[buyer_bits, doc_details]], colWidths=[104 * mm, 78 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 3 * mm))

    # ---- Parties: Supplier (Billed From) vs Company (Delivered To) ----
    supplier_addr = supplier.address or ""
    parties = Table(
        [[
            _party_block(
                styles, "SUPPLIER (BILLED FROM)", supplier.name, supplier_addr,
                supplier.gstin or "", supplier.phone or "", supplier.state, getattr(supplier, "state_code", "")
            ),
            _party_block(
                styles, "BILLED TO / DELIVERED TO (BUYER)", company.name, addr,
                company.gstin or "", company.phone or "", company.state, getattr(company, "state_code", "")
            ),
        ]],
        colWidths=[91 * mm, 91 * mm],
    )
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 2),
        ("LEFTPADDING", (1, 0), (1, 0), 2),
    ]))
    story.append(parties)
    story.append(Spacer(1, 3 * mm))

    # ---- Line Items Table ----
    data = [[
        Paragraph("S.NO.", styles["th"]),
        Paragraph("ITEMS / DESCRIPTION", styles["th"]),
        Paragraph("HSN/SAC", styles["th"]),
        Paragraph("QTY.", styles["th"]),
        Paragraph("RATE (₹)", styles["th"]),
        Paragraph("DISC %", styles["th"]),
        Paragraph("TAXABLE (₹)", styles["th"]),
        Paragraph("GST %", styles["th"]),
        Paragraph("TAX (₹)", styles["th"]),
        Paragraph("TOTAL (₹)", styles["th"]),
    ]]

    total_qty = Decimal("0")
    total_taxable = Decimal("0")
    total_tax = Decimal("0")
    total_amount = Decimal("0")

    for idx, item in enumerate(items, start=1):
        qty = Decimal(str(item.quantity))
        rate = Decimal(str(item.unit_price))
        disc = Decimal(str(getattr(item, "discount_percent", 0) or 0))
        taxable = Decimal(str(item.taxable_amount or item.line_total or 0))
        line_tax = Decimal(str(item.cgst or 0)) + Decimal(str(item.sgst or 0)) + Decimal(str(item.igst or 0)) + Decimal(str(getattr(item, "cess", 0) or 0))
        line_tot = Decimal(str(item.line_total or 0))

        total_qty += qty
        total_taxable += taxable
        total_tax += line_tax
        total_amount += line_tot

        unit = (getattr(item, "unit_name", None) or getattr(item.product.unit, "short_name", None) or "PCS").upper()
        item_cell = [Paragraph(f"<b>{pdf_esc(item.description or item.product.name)}</b>", styles["td"])]
        if item.description and item.description != item.product.name:
            item_cell.append(Paragraph(pdf_esc(item.product.name), styles["body_small"]))
        if getattr(item, "batch_no", ""):
            item_cell.append(Paragraph(f"Batch: {item.batch_no}", styles["body_small"]))

        data.append([
            Paragraph(str(idx), styles["td_center"]),
            item_cell,
            Paragraph(item.hsn_code or item.product.hsn_code or "—", styles["td_center"]),
            Paragraph(f"{format_qty(qty)} {unit}", styles["td_center"]),
            Paragraph(format_money(rate), styles["td_right"]),
            Paragraph(f"{disc}%" if disc else "—", styles["td_center"]),
            Paragraph(format_money(taxable), styles["td_right"]),
            Paragraph(f"{item.gst_rate}%", styles["td_center"]),
            Paragraph(format_money(line_tax), styles["td_right"]),
            Paragraph(format_money(line_tot), styles["td_right"]),
        ])

    # Totals Row
    data.append([
        Paragraph("<b>TOTAL</b>", styles["th"]),
        Paragraph("", styles["td"]),
        Paragraph("", styles["td"]),
        Paragraph(f"<b>{format_qty(total_qty)}</b>", styles["td_center"]),
        Paragraph("", styles["td"]),
        Paragraph("", styles["td"]),
        Paragraph(f"<b>{format_money(total_taxable)}</b>", styles["td_right"]),
        Paragraph("", styles["td"]),
        Paragraph(f"<b>{format_money(total_tax)}</b>", styles["td_right"]),
        Paragraph(f"<b>{format_money(total_amount)}</b>", styles["td_right"]),
    ])

    col_widths = [10 * mm, 46 * mm, 16 * mm, 18 * mm, 18 * mm, 14 * mm, 20 * mm, 14 * mm, 16 * mm, 20 * mm]
    item_table = Table(data, colWidths=col_widths, repeatRows=1)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREY_HEADER),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("BACKGROUND", (0, -1), (-1, -1), GREY_TOTAL),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 3 * mm))

    # ---- Summary & Amount in Words ----
    left_summary = [
        Paragraph("<b>Total Amount in Words:</b>", styles["meta"]),
        Paragraph(f"<i>{amount_in_words(invoice.grand_total)}</i>", styles["body"]),
        Spacer(1, 3 * mm),
        Paragraph("<b>Statutory GST Tax Summary (HSN/SAC Breakup):</b>", styles["meta"]),
        Spacer(1, 1 * mm),
        _build_hsn_summary_table(items, styles, intra_state),
    ]

    right_summary_rows = [
        [Paragraph("Taxable Amount:", styles["meta"]), Paragraph(format_money(invoice.taxable_total or total_taxable), styles["td_right"])],
    ]
    if intra_state:
        if invoice.cgst_total:
            right_summary_rows.append([Paragraph("CGST Total:", styles["meta"]), Paragraph(format_money(invoice.cgst_total), styles["td_right"])])
        if invoice.sgst_total:
            right_summary_rows.append([Paragraph("SGST Total:", styles["meta"]), Paragraph(format_money(invoice.sgst_total), styles["td_right"])])
    else:
        if invoice.igst_total:
            right_summary_rows.append([Paragraph("IGST Total:", styles["meta"]), Paragraph(format_money(invoice.igst_total), styles["td_right"])])
    if getattr(invoice, "cess_total", 0):
        right_summary_rows.append([Paragraph("Cess Total:", styles["meta"]), Paragraph(format_money(invoice.cess_total), styles["td_right"])])
    if getattr(invoice, "additional_charges", 0):
        right_summary_rows.append([Paragraph("Additional Charges / Freight:", styles["meta"]), Paragraph(format_money(invoice.additional_charges), styles["td_right"])])
    if getattr(invoice, "invoice_discount", 0):
        right_summary_rows.append([Paragraph("Invoice Discount:", styles["meta"]), Paragraph(f"-{format_money(invoice.invoice_discount)}", styles["td_right"])])
    if getattr(invoice, "round_off", 0):
        right_summary_rows.append([Paragraph("Round Off:", styles["meta"]), Paragraph(format_money(invoice.round_off), styles["td_right"])])

    right_summary_rows.append([
        Paragraph("<b>Grand Total (₹):</b>", styles["section_head"]),
        Paragraph(f"<b>{format_money(invoice.grand_total)}</b>", styles["td_right"]),
    ])
    right_summary_rows.append([
        Paragraph("Amount Paid / Allocated:", styles["meta"]),
        Paragraph(format_money(allocated), styles["td_right"]),
    ])
    right_summary_rows.append([
        Paragraph("<b>Balance Payable:</b>", styles["section_head"]),
        Paragraph(f"<b>{format_money(balance)}</b>", styles["td_right"]),
    ])

    summary_table_right = Table(right_summary_rows, colWidths=[46 * mm, 30 * mm])
    summary_table_right.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("BACKGROUND", (0, -3), (-1, -3), GREY_TOTAL),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    bottom_split = Table(
        [[left_summary, summary_table_right]],
        colWidths=[106 * mm, 76 * mm],
    )
    bottom_split.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([bottom_split]))
    story.append(Spacer(1, 4 * mm))

    # ---- Signatures & Verification Block ----
    sig_data = [
        [
            Paragraph("<b>Goods Receipt & Quality Verification:</b><br/>Certified that the goods/services mentioned above have been received in good condition, inspected, and entered in the stock register.", styles["body_small"]),
            Paragraph(f"<b>For {company.name}</b><br/><br/><br/><b>Authorised Signatory</b>", styles["td_center"]),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[114 * mm, 68 * mm])
    sig_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(KeepTogether([sig_table]))

    doc.build(story)
    return buffer.getvalue()


def render_gst_purchase_order(order) -> bytes:
    """Render a formal GST-compliant Purchase Order PDF."""
    company = order.company
    supplier = order.supplier
    items = list(order.items.select_related("product", "product__unit").all())
    styles = build_styles()

    from core.services.place_of_supply import party_intra_state
    intra_state = party_intra_state(company, supplier.state, supplier.gstin or "")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Purchase Order {order.number or order.pk}",
        author=company.name,
    )

    story = []

    # ---- Header ----
    buyer_bits = [
        Paragraph(f"<b>{company.name}</b>", styles["company_name"]),
    ]
    if company.gstin:
        buyer_bits.append(Paragraph(f"<b>GSTIN:</b> {company.gstin}", styles["meta"]))
    if company.phone:
        buyer_bits.append(Paragraph(f"<b>Phone:</b> {company.phone}", styles["meta"]))
    addr = _company_address(company)
    if addr:
        for line in addr.split("\n"):
            buyer_bits.append(Paragraph(line, styles["meta"]))

    doc_details = [
        Paragraph("<b>PURCHASE ORDER</b>", styles["title"]),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>PO Number:</b> {order.number or '—'}", styles["meta"]),
        Paragraph(f"<b>PO Date:</b> {order.order_date.strftime('%d/%m/%Y')}", styles["meta"]),
        Paragraph(f"<b>Status:</b> {order.get_status_display()}", styles["meta"]),
    ]
    if getattr(order, "expected_delivery_date", None):
        doc_details.append(Paragraph(f"<b>Expected Delivery:</b> {order.expected_delivery_date.strftime('%d/%m/%Y')}", styles["meta"]))

    header = Table([[buyer_bits, doc_details]], colWidths=[104 * mm, 78 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 3 * mm))

    # ---- Parties ----
    parties = Table(
        [[
            _party_block(
                styles, "SUPPLIER / VENDOR", supplier.name, supplier.address or "",
                supplier.gstin or "", supplier.phone or "", supplier.state, getattr(supplier, "state_code", "")
            ),
            _party_block(
                styles, "DELIVERY / INVOICE TO", company.name, addr,
                company.gstin or "", company.phone or "", company.state, getattr(company, "state_code", "")
            ),
        ]],
        colWidths=[91 * mm, 91 * mm],
    )
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 2),
        ("LEFTPADDING", (1, 0), (1, 0), 2),
    ]))
    story.append(parties)
    story.append(Spacer(1, 3 * mm))

    # ---- Line Items ----
    data = [[
        Paragraph("S.NO.", styles["th"]),
        Paragraph("ITEM DESCRIPTION", styles["th"]),
        Paragraph("HSN/SAC", styles["th"]),
        Paragraph("QTY.", styles["th"]),
        Paragraph("RATE (₹)", styles["th"]),
        Paragraph("TAXABLE (₹)", styles["th"]),
        Paragraph("GST %", styles["th"]),
        Paragraph("TAX (₹)", styles["th"]),
        Paragraph("TOTAL (₹)", styles["th"]),
    ]]

    for idx, item in enumerate(items, start=1):
        qty = Decimal(str(item.quantity))
        rate = Decimal(str(item.unit_price))
        taxable = Decimal(str(item.taxable_amount or item.line_total or 0))
        line_tax = Decimal(str(item.cgst or 0)) + Decimal(str(item.sgst or 0)) + Decimal(str(item.igst or 0)) + Decimal(str(getattr(item, "cess", 0) or 0))
        line_tot = Decimal(str(item.line_total or 0))

        unit = (getattr(item, "unit_name", None) or getattr(item.product.unit, "short_name", None) or "PCS").upper()
        data.append([
            Paragraph(str(idx), styles["td_center"]),
            Paragraph(f"<b>{pdf_esc(item.description or item.product.name)}</b>", styles["td"]),
            Paragraph(getattr(item, "hsn_code", None) or getattr(item.product, "hsn_code", None) or "—", styles["td_center"]),
            Paragraph(f"{format_qty(qty)} {unit}", styles["td_center"]),
            Paragraph(format_money(rate), styles["td_right"]),
            Paragraph(format_money(taxable), styles["td_right"]),
            Paragraph(f"{item.gst_rate}%", styles["td_center"]),
            Paragraph(format_money(line_tax), styles["td_right"]),
            Paragraph(format_money(line_tot), styles["td_right"]),
        ])

    col_widths = [12 * mm, 54 * mm, 18 * mm, 20 * mm, 20 * mm, 22 * mm, 16 * mm, 18 * mm, 22 * mm]
    item_table = Table(data, colWidths=col_widths, repeatRows=1)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREY_HEADER),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 3 * mm))

    # ---- Summary ----
    summary_rows = [
        [Paragraph("Taxable Subtotal:", styles["meta"]), Paragraph(format_money(order.taxable_total), styles["td_right"])],
        [Paragraph("GST Taxes:", styles["meta"]), Paragraph(format_money((order.cgst_total or 0) + (order.sgst_total or 0) + (order.igst_total or 0)), styles["td_right"])],
        [Paragraph("<b>Order Total (₹):</b>", styles["section_head"]), Paragraph(f"<b>{format_money(order.grand_total)}</b>", styles["td_right"])],
    ]
    summary_table = Table(summary_rows, colWidths=[46 * mm, 30 * mm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("BACKGROUND", (0, -1), (-1, -1), GREY_TOTAL),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    left_words = [
        Paragraph("<b>Total Amount in Words:</b>", styles["meta"]),
        Paragraph(f"<i>{amount_in_words(order.grand_total)}</i>", styles["body"]),
    ]
    bottom = Table([[left_words, summary_table]], colWidths=[106 * mm, 76 * mm])
    bottom.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([bottom]))
    story.append(Spacer(1, 5 * mm))

    sig = Table(
        [[
            Paragraph("<b>Terms & Instructions:</b><br/>1. Please send invoice and delivery challan with shipment.<br/>2. Goods subject to acceptance after store inspection.", styles["body_small"]),
            Paragraph(f"<b>For {company.name}</b><br/><br/><br/><b>Authorised Signatory</b>", styles["td_center"]),
        ]],
        colWidths=[114 * mm, 68 * mm],
    )
    sig.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(KeepTogether([sig]))

    doc.build(story)
    return buffer.getvalue()
