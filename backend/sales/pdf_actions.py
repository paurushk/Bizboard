"""Shared pdf-status / pdf / regenerate-pdf actions for note/challan viewsets."""


from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.celery_utils import safe_delay
from core.exceptions import BusinessRuleError

from .models import SalesInvoice


class PdfDocumentActionsMixin:
    """Expects subclasses to set pdf_task and completed_statuses."""

    pdf_task = None
    completed_statuses = ()

    @action(detail=True, methods=["post"], url_path="regenerate-pdf")
    def regenerate_pdf(self, request, pk=None):
        doc = self.get_object()
        if doc.status not in self.completed_statuses:
            raise BusinessRuleError("PDF can only be regenerated for completed documents.")
        doc.pdf_status = SalesInvoice.PdfStatus.QUEUED
        doc.save(update_fields=["pdf_status"])
        safe_delay(self.pdf_task, doc.pk, company_id=doc.company_id)
        doc.refresh_from_db()
        return Response({"pdf_status": doc.pdf_status, "pdf_file": doc.pdf_file_id})

    @action(detail=True, methods=["get"], url_path="pdf-status")
    def pdf_status(self, request, pk=None):
        doc = self.get_object()
        return Response({"pdf_status": doc.pdf_status, "pdf_file": doc.pdf_file_id})

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        doc = self.get_object()
        if doc.status not in self.completed_statuses:
            raise BusinessRuleError("PDF is not ready for this document.")
        if doc.pdf_status != SalesInvoice.PdfStatus.READY or not doc.pdf_file:
            should_enqueue = doc.pdf_status in (
                SalesInvoice.PdfStatus.NONE,
                SalesInvoice.PdfStatus.FAILED,
            ) or (doc.pdf_status == SalesInvoice.PdfStatus.READY and not doc.pdf_file)
            if should_enqueue:
                doc.pdf_status = SalesInvoice.PdfStatus.QUEUED
                doc.save(update_fields=["pdf_status"])
                safe_delay(self.pdf_task, doc.pk, company_id=doc.company_id)
            return Response(
                {
                    "detail": "PDF is generating, retry shortly",
                    "pdf_status": doc.pdf_status,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return FileResponse(
            doc.pdf_file.file.open("rb"),
            as_attachment=True,
            filename=doc.pdf_file.original_name,
            content_type="application/pdf",
        )
