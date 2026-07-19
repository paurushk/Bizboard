"""Async PDF generation — billing never waits on rendering (§14)."""

import io

from celery import shared_task


def _render_invoice_pdf(invoice) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    company = invoice.company

    y = height - 20 * mm
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(20 * mm, y, company.name)
    pdf.setFont("Helvetica", 9)
    y -= 6 * mm
    if company.gstin:
        pdf.drawString(20 * mm, y, f"GSTIN: {company.gstin}")
        y -= 5 * mm
    if company.address:
        pdf.drawString(20 * mm, y, company.address[:100])
        y -= 5 * mm

    y -= 4 * mm
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(20 * mm, y, invoice.get_invoice_type_display())
    pdf.setFont("Helvetica", 10)
    y -= 7 * mm
    pdf.drawString(20 * mm, y, f"Invoice No: {invoice.number}    Date: {invoice.invoice_date}")
    y -= 6 * mm
    pdf.drawString(20 * mm, y, f"Bill To: {invoice.customer.name}")
    if invoice.customer.gstin:
        y -= 5 * mm
        pdf.drawString(20 * mm, y, f"Customer GSTIN: {invoice.customer.gstin}")

    y -= 10 * mm
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(20 * mm, y, "Item")
    pdf.drawString(85 * mm, y, "HSN")
    pdf.drawString(105 * mm, y, "Qty")
    pdf.drawString(125 * mm, y, "Rate")
    pdf.drawString(145 * mm, y, "Taxable")
    pdf.drawString(170 * mm, y, "Total")
    pdf.setFont("Helvetica", 9)
    for item in invoice.items.select_related("product"):
        y -= 6 * mm
        if y < 40 * mm:
            pdf.showPage()
            y = height - 20 * mm
        pdf.drawString(20 * mm, y, item.description[:38])
        pdf.drawString(85 * mm, y, item.product.hsn_code or "-")
        pdf.drawString(105 * mm, y, f"{item.quantity}")
        pdf.drawString(125 * mm, y, f"{item.unit_price}")
        pdf.drawString(145 * mm, y, f"{item.taxable_amount}")
        pdf.drawString(170 * mm, y, f"{item.line_total}")

    y -= 10 * mm
    pdf.setFont("Helvetica-Bold", 10)
    for label, value in [
        ("Taxable", invoice.taxable_total),
        ("CGST", invoice.cgst_total),
        ("SGST", invoice.sgst_total),
        ("IGST", invoice.igst_total),
        ("Round off", invoice.round_off),
        ("Grand Total", invoice.grand_total),
    ]:
        pdf.drawString(125 * mm, y, label)
        pdf.drawRightString(190 * mm, y, f"{value}")
        y -= 6 * mm

    if company.upi_id:
        pdf.setFont("Helvetica", 8)
        pdf.drawString(20 * mm, 25 * mm, f"Pay via UPI: {company.upi_id}")
    if company.invoice_terms:
        pdf.setFont("Helvetica", 7)
        pdf.drawString(20 * mm, 20 * mm, company.invoice_terms[:150])

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@shared_task
def generate_invoice_pdf(invoice_id):
    from core.models import FileAsset
    from core.services.files import FileService

    from .models import SalesInvoice

    invoice = SalesInvoice.objects.select_related("company", "customer").get(pk=invoice_id)
    try:
        content = _render_invoice_pdf(invoice)
        asset = FileService.store_bytes(
            company=invoice.company,
            content=content,
            filename=f"{invoice.number or invoice.pk}.pdf",
            kind=FileAsset.Kind.INVOICE_PDF,
            content_type="application/pdf",
        )
        invoice.pdf_file = asset
        invoice.pdf_status = SalesInvoice.PdfStatus.READY
        invoice.save(update_fields=["pdf_file", "pdf_status"])
    except Exception:
        invoice.pdf_status = SalesInvoice.PdfStatus.FAILED
        invoice.save(update_fields=["pdf_status"])
        raise
