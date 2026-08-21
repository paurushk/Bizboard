"""Async PDF generation — billing never waits on rendering (§14)."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _store_doc_pdf(*, company, content, filename, kind, document, status_field="pdf_status"):
    from core.services.files import FileService

    previous = document.pdf_file
    asset = FileService.store_bytes(
        company=company,
        content=content,
        filename=filename,
        kind=kind,
        content_type="application/pdf",
    )
    document.pdf_file = asset
    document.pdf_status = document.PdfStatus.READY if hasattr(document, "PdfStatus") else "READY"
    # SalesInvoice.PdfStatus is reused on note models
    from .models import SalesInvoice

    document.pdf_status = SalesInvoice.PdfStatus.READY
    document.save(update_fields=["pdf_file", "pdf_status"])
    if previous and previous.pk != asset.pk:
        try:
            previous.delete()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to delete prior PDF asset %s", previous.pk)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_invoice_pdf(self, invoice_id):
    from core.models import FileAsset

    from .models import SalesInvoice
    from .pdf import render_gst_tax_invoice

    try:
        invoice = SalesInvoice.objects.select_related(
            "company", "customer", "company__logo", "signature",
        ).prefetch_related("items__product__unit").get(pk=invoice_id)
    except SalesInvoice.DoesNotExist:
        return

    try:
        content = render_gst_tax_invoice(invoice, copy="ORIGINAL")
        _store_doc_pdf(
            company=invoice.company,
            content=content,
            filename=f"{invoice.number or invoice.pk}.pdf",
            kind=FileAsset.Kind.INVOICE_PDF,
            document=invoice,
        )
    except Exception:
        logger.exception("PDF generation failed for invoice %s", invoice_id)
        invoice.pdf_status = SalesInvoice.PdfStatus.FAILED
        invoice.save(update_fields=["pdf_status"])


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_credit_note_pdf(self, note_id):
    from core.models import FileAsset

    from .models import SalesCreditNote, SalesInvoice
    from .pdf import render_credit_note

    try:
        note = SalesCreditNote.objects.select_related(
            "company", "customer", "sales_invoice",
        ).prefetch_related("items__product").get(pk=note_id)
    except SalesCreditNote.DoesNotExist:
        return
    try:
        content = render_credit_note(note)
        _store_doc_pdf(
            company=note.company,
            content=content,
            filename=f"{note.number or note.pk}.pdf",
            kind=FileAsset.Kind.CREDIT_NOTE_PDF,
            document=note,
        )
    except Exception:
        logger.exception("PDF generation failed for credit note %s", note_id)
        note.pdf_status = SalesInvoice.PdfStatus.FAILED
        note.save(update_fields=["pdf_status"])


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_debit_note_pdf(self, note_id):
    from core.models import FileAsset

    from .models import SalesDebitNote, SalesInvoice
    from .pdf import render_debit_note

    try:
        note = SalesDebitNote.objects.select_related(
            "company", "customer", "sales_invoice",
        ).prefetch_related("items__product").get(pk=note_id)
    except SalesDebitNote.DoesNotExist:
        return
    try:
        content = render_debit_note(note)
        _store_doc_pdf(
            company=note.company,
            content=content,
            filename=f"{note.number or note.pk}.pdf",
            kind=FileAsset.Kind.DEBIT_NOTE_PDF,
            document=note,
        )
    except Exception:
        logger.exception("PDF generation failed for debit note %s", note_id)
        note.pdf_status = SalesInvoice.PdfStatus.FAILED
        note.save(update_fields=["pdf_status"])


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_challan_pdf(self, challan_id):
    from core.models import FileAsset

    from .models import DeliveryChallan, SalesInvoice
    from .pdf import render_delivery_challan

    try:
        challan = DeliveryChallan.objects.select_related(
            "company", "customer", "sales_order",
        ).prefetch_related("items__product").get(pk=challan_id)
    except DeliveryChallan.DoesNotExist:
        return
    try:
        content = render_delivery_challan(challan)
        _store_doc_pdf(
            company=challan.company,
            content=content,
            filename=f"{challan.number or challan.pk}.pdf",
            kind=FileAsset.Kind.CHALLAN_PDF,
            document=challan,
        )
    except Exception:
        logger.exception("PDF generation failed for challan %s", challan_id)
        challan.pdf_status = SalesInvoice.PdfStatus.FAILED
        challan.save(update_fields=["pdf_status"])


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def submit_einvoice_async(self, invoice_id: int, user_id: int | None = None):
    """Wave 17A: async IRP submit with idempotency (skip if IRN already set)."""
    from accounts.models import User
    from core.services.audit import AuditService
    from core.services.gsp_adapters import get_irp_adapter, verify_irn_result

    from .einvoice_payload import EinvoiceValidationError, build_einvoice_payload
    from .models import SalesInvoice

    try:
        invoice = SalesInvoice.objects.select_related("company", "customer").get(pk=invoice_id)
    except SalesInvoice.DoesNotExist:
        return {"status": "missing"}
    if invoice.irn:
        return {"status": "already_generated", "irn": invoice.irn}
    try:
        payload = build_einvoice_payload(invoice)
        result = get_irp_adapter(invoice.company).submit(payload)
        verify_irn_result(result)
    except EinvoiceValidationError as exc:
        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
        invoice.einvoice_error = "; ".join(exc.errors)
        invoice.save(update_fields=["einvoice_status", "einvoice_error"])
        return {"status": "validation_failed", "errors": exc.errors}
    except Exception as exc:
        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
        invoice.einvoice_error = str(exc)[:500]
        invoice.save(update_fields=["einvoice_status", "einvoice_error"])
        raise
    invoice.irn = result.irn
    invoice.ack_no = result.ack_no
    invoice.ack_date = result.ack_date
    invoice.einvoice_qr = result.einvoice_qr
    invoice.einvoice_status = SalesInvoice.EInvoiceStatus.GENERATED
    invoice.einvoice_error = ""
    invoice.save(
        update_fields=[
            "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error",
        ]
    )
    user = User.objects.filter(pk=user_id).first() if user_id else None
    AuditService.log(
        company=invoice.company,
        user=user,
        action="UPDATE",
        entity_type="salesinvoice",
        entity_id=invoice.pk,
        description="einvoice.submitted_async",
        metadata={"irn": result.irn},
    )
    return {"status": "generated", "irn": result.irn}


@shared_task
def generate_recurring_invoices_task():
    """BB-000669: beat entry — create DRAFT invoices for due schedules."""
    from .recurring import process_due_schedules

    return process_due_schedules()
