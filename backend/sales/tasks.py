"""Async PDF generation — billing never waits on rendering (§14)."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_invoice_pdf(self, invoice_id):
    from core.models import FileAsset
    from core.services.files import FileService

    from .models import SalesInvoice
    from .pdf import render_gst_tax_invoice

    try:
        invoice = SalesInvoice.objects.select_related(
            "company", "customer", "company__logo", "signature",
        ).prefetch_related("items__product__unit").get(pk=invoice_id)
    except SalesInvoice.DoesNotExist:
        return

    try:
        # Stored asset is always ORIGINAL; DUPLICATE is rendered on download.
        content = render_gst_tax_invoice(invoice, copy="ORIGINAL")
        previous = invoice.pdf_file
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
        if previous and previous.pk != asset.pk:
            try:
                previous.delete()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                logger.exception("Failed to delete prior PDF asset %s", previous.pk)
    except Exception:
        logger.exception("PDF generation failed for invoice %s", invoice_id)
        invoice.pdf_status = SalesInvoice.PdfStatus.FAILED
        invoice.save(update_fields=["pdf_status"])
        # Do not re-raise — Complete must survive PDF failure.
