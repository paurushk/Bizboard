"""Async purchase/sales-bill extraction via configured LLM."""

from celery import shared_task

# Batch pages sent per LLM call — keeps a single request's payload bounded
# even when a bill runs to dozens of pages (Bill Import Redesign Plan §7 Phase 3).
EXTRACT_BATCH_SIZE = 5


def _file_to_images(raw: bytes, content_type: str, filename: str) -> list[bytes]:
    from django.conf import settings

    from core.exceptions import BusinessRuleError

    ctype = (content_type or "").lower()
    name = (filename or "").lower()
    soft_cap = int(getattr(settings, "LLM_BILL_MAX_PAGES", 20) or 20)
    hard_cap = int(getattr(settings, "LLM_BILL_MAX_PAGES_HARD", 50) or 50)

    is_pdf = ctype == "application/pdf" or name.endswith(".pdf")
    if is_pdf:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(raw)
        page_count = len(pdf)
        if page_count > hard_cap:
            raise BusinessRuleError(
                f"PDF has {page_count} pages, over the {hard_cap}-page limit — this is "
                "almost never a genuine bill. Split it or upload the relevant pages only."
            )
        pages_to_read = min(page_count, soft_cap)
        images = []
        for index in range(pages_to_read):
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


def _merge_extraction_payloads(payloads: list[dict]) -> dict:
    """Merge per-batch extraction results (multi-page PDFs, §7 Phase 3) into a
    single payload — header fields from the first batch that has them, lines
    concatenated in page order, confidence the minimum across batches."""
    if len(payloads) == 1:
        return payloads[0]
    merged = {
        "supplier_name": "", "supplier_gstin": "", "buyer_name": "", "buyer_gstin": "",
        "bill_number": "", "bill_date": "", "confidence": None,
        "printed_line_count": None, "column_headers": [], "lines": [],
    }
    confidences = []
    seen_headers: list[str] = []
    line_counts = []
    for payload in payloads:
        for field in ("supplier_name", "supplier_gstin", "buyer_name", "buyer_gstin", "bill_number", "bill_date"):
            if not merged[field] and payload.get(field):
                merged[field] = payload[field]
        if payload.get("printed_line_count") not in (None, ""):
            line_counts.append(payload["printed_line_count"])
        for header in payload.get("column_headers") or []:
            if header not in seen_headers:
                seen_headers.append(header)
        merged["lines"].extend(payload.get("lines") or [])
        if payload.get("confidence") is not None:
            confidences.append(payload["confidence"])
    merged["column_headers"] = seen_headers
    merged["confidence"] = min(confidences) if confidences else None
    if line_counts:
        try:
            merged["printed_line_count"] = max(int(c) for c in line_counts)
        except (TypeError, ValueError):
            merged["printed_line_count"] = line_counts[0]
    return merged


# BUG-306: cap total task runtime so a hung/slow LLM provider can't wedge a
# worker (and the ImportJob) forever — soft limit raises inside the task so
# the except below can still mark the job FAILED cleanly.
# Two high-detail vision calls at 120s each need more than the original 180s.
@shared_task(time_limit=360, soft_time_limit=330)
def extract_purchase_bill_task(job_id: int):
    from celery.exceptions import SoftTimeLimitExceeded
    from core.exceptions import BusinessRuleError
    from core.services.llm import extract_purchase_bill
    from imports.models import ImportJob
    from imports.services import BillImportService

    try:
        job = ImportJob.objects.select_related("file", "company").get(pk=job_id)
    except ImportJob.DoesNotExist:
        return

    if job.kind not in ImportJob.BILL_KINDS:
        return
    if job.status not in (ImportJob.Status.EXTRACTING, ImportJob.Status.UPLOADED):
        return

    try:
        asset = job.file
        with asset.file.open("rb") as handle:
            raw = handle.read()
        images = _file_to_images(raw, asset.content_type, asset.original_name or asset.file.name)
        if len(images) > EXTRACT_BATCH_SIZE:
            batches = [
                images[i:i + EXTRACT_BATCH_SIZE]
                for i in range(0, len(images), EXTRACT_BATCH_SIZE)
            ]
            payload = _merge_extraction_payloads([extract_purchase_bill(batch) for batch in batches])
        else:
            payload = extract_purchase_bill(images)
        BillImportService.apply_extraction(job, payload)
    except BusinessRuleError as exc:
        BillImportService.mark_failed(job, str(exc.detail if hasattr(exc, "detail") else exc))
    except SoftTimeLimitExceeded:
        BillImportService.mark_failed(job, "Extraction timed out — please retry.")
    except Exception as exc:  # noqa: BLE001 — surface to job failure_reason
        BillImportService.mark_failed(job, str(exc))
