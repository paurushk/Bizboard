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


def _retries_left(task) -> bool:
    retries = int(getattr(getattr(task, "request", None), "retries", 0) or 0)
    limit = int(getattr(task, "max_retries", 0) or 0)
    return retries < limit


def _mark_pdf_for_retry(document) -> None:
    from .models import SalesInvoice

    document.pdf_status = SalesInvoice.PdfStatus.QUEUED
    document.save(update_fields=["pdf_status"])


def _mark_pdf_failed(document) -> None:
    from .models import SalesInvoice

    document.pdf_status = SalesInvoice.PdfStatus.FAILED
    document.save(update_fields=["pdf_status"])


def _notify_pdf_failed(document, kind: str) -> None:
    """One in-app note when rendering has used its Celery retries."""
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService

    label = document.number or document.pk
    body = f"The {kind} PDF for {label} could not be rendered."
    owners = CompanyUser.objects.filter(
        company=document.company, is_active=True, role=CompanyUser.Role.OWNER,
    ).select_related("user")
    for membership in owners:
        try:
            NotificationService.send(
                company=document.company,
                channel=Notification.Channel.IN_APP,
                recipient=membership.user.email or str(membership.user_id),
                subject="PDF failed",
                body=body,
                user=membership.user,
            )
        except Exception:
            logger.exception("pdf failed notify company=%s", document.company_id)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_invoice_pdf(self, invoice_id, company_id=None):
    from core.models import FileAsset

    from .models import SalesInvoice
    from .pdf import render_gst_tax_invoice

    try:
        qs = SalesInvoice.objects.select_related(
            "company", "customer", "company__logo", "signature", "company_gstin",
        ).prefetch_related("items__product__unit")
        if company_id:
            invoice = qs.get(pk=invoice_id, company_id=company_id)
        else:
            invoice = qs.get(pk=invoice_id)
    except SalesInvoice.DoesNotExist:
        return

    try:
        from core.tracing import trace_span

        with trace_span("sales.pdf", invoice_id=invoice.pk, company_id=invoice.company_id):
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
        if _retries_left(self):
            _mark_pdf_for_retry(invoice)
            raise
        _mark_pdf_failed(invoice)
        try:
            from insights.telemetry import record_pdf_failed

            record_pdf_failed(invoice.company)
        except Exception:  # noqa: BLE001 — telemetry must not hide the PDF failure
            pass
        _notify_pdf_failed(invoice, "invoice")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_credit_note_pdf(self, note_id, company_id=None):
    from core.models import FileAsset

    from .models import SalesCreditNote
    from .pdf import render_credit_note

    try:
        qs = SalesCreditNote.objects.select_related(
            "company", "customer", "sales_invoice",
        ).prefetch_related("items__product")
        if company_id:
            note = qs.get(pk=note_id, company_id=company_id)
        else:
            note = qs.get(pk=note_id)
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
        if _retries_left(self):
            _mark_pdf_for_retry(note)
            raise
        _mark_pdf_failed(note)
        _notify_pdf_failed(note, "credit note")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_debit_note_pdf(self, note_id, company_id=None):
    from core.models import FileAsset

    from .models import SalesDebitNote
    from .pdf import render_debit_note

    try:
        qs = SalesDebitNote.objects.select_related(
            "company", "customer", "sales_invoice",
        ).prefetch_related("items__product")
        if company_id:
            note = qs.get(pk=note_id, company_id=company_id)
        else:
            note = qs.get(pk=note_id)
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
        if _retries_left(self):
            _mark_pdf_for_retry(note)
            raise
        _mark_pdf_failed(note)
        _notify_pdf_failed(note, "debit note")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_challan_pdf(self, challan_id, company_id=None):
    from core.models import FileAsset

    from .models import DeliveryChallan
    from .pdf import render_delivery_challan

    qs = DeliveryChallan.objects.select_related(
        "company", "customer", "sales_order",
    ).prefetch_related("items__product")
    try:
        # B2-016: honour the tenant-scope guard the sibling PDF tasks apply.
        challan = qs.get(pk=challan_id, company_id=company_id) if company_id else qs.get(pk=challan_id)
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
        if _retries_left(self):
            _mark_pdf_for_retry(challan)
            raise
        _mark_pdf_failed(challan)
        _notify_pdf_failed(challan, "delivery challan")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def submit_einvoice_async(self, invoice_id: int, user_id: int | None = None, company_id=None):
    """Wave 17A: async IRP submit with idempotency (skip if IRN already set)."""
    from accounts.models import User
    from core.services.audit import AuditService
    from core.services.gsp_adapters import get_irp_adapter, plain_gsp_error, verify_irn_result

    from .einvoice_payload import EinvoiceValidationError, build_einvoice_payload
    from .models import SalesInvoice

    try:
        qs = SalesInvoice.objects.select_related("company", "customer")
        if company_id:
            invoice = qs.get(pk=invoice_id, company_id=company_id)
        else:
            invoice = qs.get(pk=invoice_id)
    except SalesInvoice.DoesNotExist:
        return {"status": "missing"}
    if invoice.irn:
        return {"status": "already_generated", "irn": invoice.irn}
    try:
        payload = build_einvoice_payload(invoice)
        adapter = get_irp_adapter(invoice.company)
        lookup = getattr(adapter, "lookup_by_doc", None)
        found = lookup(invoice.number) if lookup and invoice.number else None
        if found is not None and isinstance(getattr(found, "irn", None), str) and found.irn:
            result = found
        else:
            result = adapter.submit(payload)
        verify_irn_result(result)
    except EinvoiceValidationError as exc:
        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
        invoice.einvoice_error = plain_gsp_error("; ".join(exc.errors))
        invoice.save(update_fields=["einvoice_status", "einvoice_error"])
        return {"status": "validation_failed", "errors": exc.errors}
    except Exception as exc:
        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
        invoice.einvoice_error = plain_gsp_error(str(exc))
        invoice.save(update_fields=["einvoice_status", "einvoice_error"])
        raise
    from django.db import transaction

    with transaction.atomic():
        locked = SalesInvoice.objects.select_for_update().get(pk=invoice_id)
        if locked.irn:
            return {"status": "already_generated", "irn": locked.irn}
        locked.irn = result.irn
        locked.ack_no = result.ack_no
        locked.ack_date = result.ack_date
        locked.einvoice_qr = result.einvoice_qr
        locked.einvoice_status = SalesInvoice.EInvoiceStatus.GENERATED
        locked.einvoice_error = ""
        locked.save(
            update_fields=[
                "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error",
            ]
        )
        invoice = locked
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
def suggest_route_sequence_task(route_id, strategy_name, company_id):
    """Recompute a slow route suggestion off the request. The HTTP call stays 200 unless deferred."""
    from .models import DeliveryRoute
    from .route_service import RouteService

    route = DeliveryRoute.objects.filter(pk=route_id, company_id=company_id).first()
    if route is None:
        return {"status": "missing"}
    suggestion = RouteService.suggest_stop_sequence(route, strategy_name=strategy_name or None)
    from django.core.cache import cache

    cache.set(
        f"route-seq-result:{route_id}",
        _cached_sequence(suggestion),
        600,
    )
    return {"status": "ready", "stops": len(suggestion)}


def _cached_sequence(suggestion):
    return [
        {
            "stop_id": stop.stop_id,
            "sequence": stop.sequence,
            "pincode": getattr(stop, "pincode", ""),
            "needs_manual_sequencing": bool(getattr(stop, "needs_manual_sequencing", False)),
        }
        for stop in suggestion
    ]


@shared_task
def requeue_stale_invoice_pdfs():
    """FMEA-012: a dead worker leaves pdf_status QUEUED. Requeue and tell the owner once."""
    from datetime import timedelta

    from django.core.cache import cache
    from django.utils import timezone

    from core.services.telegram import notify_company_owners

    from .models import SalesInvoice

    from core.rls import rls_bypass

    cutoff = timezone.now() - timedelta(minutes=15)
    # A cross-tenant sweep: under row-level security it sees nothing without the bypass.
    with rls_bypass():
        stale = list(
            SalesInvoice.objects.filter(
                pdf_status=SalesInvoice.PdfStatus.QUEUED,
                updated_at__lt=cutoff,
            ).select_related("company")[:50]
        )
        for invoice in stale:
            generate_invoice_pdf.delay(invoice.pk, company_id=invoice.company_id)
            key = f"pdf-stale-notified:{invoice.pk}"
            if cache.add(key, "1", timeout=24 * 60 * 60):
                notify_company_owners(
                    invoice.company,
                    subject="Invoice PDF still queued",
                    body=f"Invoice {invoice.number or invoice.pk} has been waiting on its PDF.",
                )
    return {"requeued": len(stale)}


@shared_task
def generate_recurring_invoices_task():
    """BB-000669: beat entry — create DRAFT invoices for due schedules."""
    from .recurring import process_due_schedules

    return process_due_schedules()


@shared_task
def purge_old_invoice_zips_task(days: int = 7) -> int:
    """Delete bulk invoice zips older than ``days``. They are built on demand and never needed again."""
    from datetime import timedelta

    from django.utils import timezone

    from core.models import FileAsset

    old = FileAsset.objects.filter(
        kind=FileAsset.Kind.EXPORT,
        original_name="invoices.zip",
        created_at__lt=timezone.now() - timedelta(days=days),
    )
    removed = 0
    for asset in old.iterator():
        try:
            asset.file.delete(save=False)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to remove zip file for asset %s", asset.pk)
        asset.delete()
        removed += 1
    return removed


@shared_task
def sweep_quotation_conversions() -> dict:
    """Nightly: give converted quantity back when its order or invoice is gone or cancelled."""
    from .quotation_conversions import QuotationConversionService

    result = QuotationConversionService.sweep()
    if result["released"]:
        logger.warning("quotation conversion sweep released %s row(s): %s", result["released"], result["by_reason"])
    return result
