"""Async purchase-bill extraction via configured LLM."""

from celery import shared_task


def _file_to_images(raw: bytes, content_type: str, filename: str) -> list[bytes]:
    from django.conf import settings

    ctype = (content_type or "").lower()
    name = (filename or "").lower()
    max_pages = int(getattr(settings, "LLM_BILL_MAX_PAGES", 5) or 5)

    is_pdf = ctype == "application/pdf" or name.endswith(".pdf")
    if is_pdf:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(raw)
        images = []
        for index in range(min(len(pdf), max_pages)):
            page = pdf[index]
            bitmap = page.render(scale=2)
            pil_image = bitmap.to_pil()
            from io import BytesIO

            buf = BytesIO()
            pil_image.save(buf, format="PNG")
            images.append(buf.getvalue())
        if not images:
            raise ValueError("PDF has no pages to extract.")
        return images

    # Treat everything else as a single image.
    if not raw:
        raise ValueError("Uploaded file is empty.")
    return [raw]


@shared_task
def extract_purchase_bill_task(job_id: int):
    from core.exceptions import BusinessRuleError
    from core.services.llm import extract_purchase_bill
    from imports.models import ImportJob
    from imports.services import BillImportService

    try:
        job = ImportJob.objects.select_related("file", "company").get(pk=job_id)
    except ImportJob.DoesNotExist:
        return

    if job.kind != ImportJob.Kind.PURCHASE_BILL:
        return
    if job.status not in (ImportJob.Status.EXTRACTING, ImportJob.Status.UPLOADED):
        return

    try:
        asset = job.file
        with asset.file.open("rb") as handle:
            raw = handle.read()
        images = _file_to_images(raw, asset.content_type, asset.original_name or asset.file.name)
        payload = extract_purchase_bill(images)
        BillImportService.apply_extraction(job, payload)
    except BusinessRuleError as exc:
        BillImportService.mark_failed(job, str(exc.detail if hasattr(exc, "detail") else exc))
    except Exception as exc:  # noqa: BLE001 — surface to job failure_reason
        BillImportService.mark_failed(job, str(exc))
