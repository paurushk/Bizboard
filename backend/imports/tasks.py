"""Async purchase/sales-bill extraction via configured LLM."""

import logging

from celery import shared_task

logger = logging.getLogger("imports.extract")

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
        if page_count > soft_cap:
            raise BusinessRuleError(
                f"PDF has {page_count} pages (limit {soft_cap}). Split the bill into smaller files."
            )
        pages_to_read = page_count
        images = []
        # B3-010: clamp the render scale so a page with a huge media box can't
        # rasterise to a multi-hundred-megapixel bitmap and OOM the worker. Cap
        # the long edge at ~2600 px; reject an absurd page outright.
        MAX_LONG_EDGE_PX = 2600
        MAX_PAGE_POINTS = 20000  # ~278 inches — nothing legitimate is this big
        for index in range(pages_to_read):
            page = pdf[index]
            try:
                pw, ph = float(page.get_width()), float(page.get_height())
            except Exception:
                pw = ph = 0.0
            long_pts = max(pw, ph)
            if long_pts > MAX_PAGE_POINTS:
                raise BusinessRuleError(
                    f"PDF page {index + 1} is {long_pts:.0f}pt on its long edge — "
                    "that is not a scannable bill."
                )
            scale = 2.0
            if long_pts > 0:
                scale = min(2.0, MAX_LONG_EDGE_PX / long_pts)
                scale = max(scale, 0.25)
            bitmap = page.render(scale=scale)
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
        "freight": "", "invoice_discount": "", "price_mode_hint": "",
    }
    confidences = []
    seen_headers: list[str] = []
    line_counts = []
    for payload in payloads:
        for field in (
            "supplier_name", "supplier_gstin", "buyer_name", "buyer_gstin", "bill_number", "bill_date",
            "freight", "invoice_discount", "price_mode_hint",
        ):
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
    if any(p.get("injection_flagged") for p in payloads):
        merged["injection_flagged"] = True
        merged["confidence"] = 0.0
    if line_counts:
        try:
            merged["printed_line_count"] = max(int(c) for c in line_counts)
        except (TypeError, ValueError):
            merged["printed_line_count"] = line_counts[0]
    return merged


# BUG-306: cap total task runtime so a hung/slow LLM provider can't wedge a
# worker (and the ImportJob) forever — soft limit raises inside the task so
# the except below can still mark the job FAILED cleanly.
# Four SI-window vision calls (gpt-4o, high detail, table crops) need headroom
# beyond a single 180s shot — still fail the job cleanly on the soft limit.
@shared_task(time_limit=480, soft_time_limit=450)
def extract_purchase_bill_task(job_id: int, company_id=None):
    from celery.exceptions import SoftTimeLimitExceeded
    from django.utils import timezone

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
        # B7-016: this job has real per-call LLM token cost and previously had
        # no ceiling at all -- gate it on the same company-wide AI budget the
        # assistant chat feature already enforces (insights.assistant), so a
        # company that has exhausted its monthly allowance can't keep kicking
        # off extraction jobs.
        from insights.assistant import assert_within_budget

        try:
            assert_within_budget(job.company)
        except BusinessRuleError as exc:
            # 4.3: say what is exhausted (the allowance is shared with the AI
            # assistant) and what the user can do instead of a bare token count.
            raise BusinessRuleError(
                "Bill reading is paused: this month's AI allowance is used up (it is shared "
                "with the AI assistant). Ask the owner to raise it in Settings, enter the bill "
                "by hand, or upload a CSV/Excel export, which needs no AI."
            ) from exc
        asset = job.file
        with asset.file.open("rb") as handle:
            raw = handle.read()
        images = _file_to_images(raw, asset.content_type, asset.original_name or asset.file.name)
        if len(images) > EXTRACT_BATCH_SIZE:
            batches = [
                images[i:i + EXTRACT_BATCH_SIZE]
                for i in range(0, len(images), EXTRACT_BATCH_SIZE)
            ]
            # 23.13: a plain loop (not a comprehension) so the job's heartbeat
            # is refreshed, and a user cancel is honoured, between batches.
            payloads = []
            for batch in batches:
                job.refresh_from_db(fields=["status"])
                if job.status == ImportJob.Status.CANCELLED:
                    return
                payloads.append(extract_purchase_bill(batch))
                ImportJob.objects.filter(pk=job.pk).update(extraction_heartbeat_at=timezone.now())
            payload = _merge_extraction_payloads(payloads)
        else:
            payload = extract_purchase_bill(images)
        job.refresh_from_db(fields=["status"])
        if job.status == ImportJob.Status.CANCELLED:
            return
        logger.info(
            "Bill extract job=%s lines=%s printed_line_count=%s",
            job_id,
            len(payload.get("lines") or []),
            payload.get("printed_line_count"),
        )
        BillImportService.apply_extraction(job, payload)
    except BusinessRuleError as exc:
        BillImportService.mark_failed(job, str(exc.detail if hasattr(exc, "detail") else exc))
    except SoftTimeLimitExceeded:
        BillImportService.mark_failed(job, "Extraction timed out — please retry.")
    except Exception as exc:  # noqa: BLE001 — surface to job failure_reason
        BillImportService.mark_failed(job, str(exc))
