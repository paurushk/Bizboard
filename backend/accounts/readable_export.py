"""WP-DL1: a readable, versioned export a customer can open in Excel or load into other software.

The encrypted export (``tenant_backup.encrypt_export_zip``) stays the way to restore into Bizboard.
This one is a plain ZIP:

- ``manifest.json`` — format name and version, company, when it was made, and for every file its
  row count and SHA-256 (so a customer or their accountant can check nothing changed);
- one CSV per section with stable column names (UTF-8 with a BOM, so Excel shows Hindi correctly);
- ``pdf/`` — the GST tax invoice PDF of each completed sales invoice (up to ``MAX_INVOICE_PDFS``;
  the README says when there were more);
- ``README.txt`` — what is in the ZIP, in English and Hindi.

Version rule (``docs/help/DATA_EXPORT_FORMAT.md``): adding a column or section is a minor bump;
renaming or removing one is a major bump with notice. ``tests/test_readable_export_dl1.py`` pins
the columns of the main sections, so a change to them fails until the version is bumped.

Built by a Celery task on the ``reports`` queue; the owner downloads it with a link that works for
``LINK_HOURS`` hours, after a password (and two-step) check. Each export is a closed ACCESS row on
the privacy request register (WP-CP2).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import zipfile
from datetime import timedelta

from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger(__name__)

FORMAT_NAME = "bizboard-readable-export"
FORMAT_VERSION = "1.0"
LINK_HOURS = 24
MAX_INVOICE_PDFS = 500
# A PENDING export older than this is a build that died (worker restart, OOM, broker down); it no
# longer blocks a new request and the daily purge marks it failed. Above the task's hard limit.
STALE_PENDING_MINUTES = 30
_SKIP_SECTIONS = {"company", "file_asset_warnings"}
# Columns that are file contents, not data: a base64 blob in a CSV cell breaks Excel (32,767 chars).
_DROP_COLUMNS = {"file_assets": {"bytes_b64"}}

README_EN = """Bizboard data export
====================

This ZIP holds your company's data from Bizboard as CSV files you can open in Excel, Google
Sheets or your accounting software, plus PDFs of your GST tax invoices.

- manifest.json lists every file with its row count and a SHA-256 checksum.
- Each CSV has one row per record. Amounts are in rupees; dates are YYYY-MM-DD.
- pdf/ holds a PDF of each completed sales invoice{pdf_note}.
- Format version {version}. The columns are described at docs/help/DATA_EXPORT_FORMAT.md
  (Help -> Your data -> Export format in the app).

To move back into Bizboard, use the encrypted backup from Settings -> Backup instead.
"""

README_HI = """Bizboard डेटा निर्यात
====================

इस ZIP में Bizboard से आपकी कंपनी का डेटा CSV फ़ाइलों में है, जिन्हें आप Excel, Google Sheets या
अपने अकाउंटिंग सॉफ़्टवेयर में खोल सकते हैं, और आपके GST टैक्स इनवॉइस के PDF हैं।

- manifest.json में हर फ़ाइल, उसकी पंक्तियों की संख्या और SHA-256 चेकसम है।
- हर CSV में हर रिकॉर्ड की एक पंक्ति है। रकम रुपये में है; तारीख YYYY-MM-DD में है।
- pdf/ में हर पूरे हुए बिक्री इनवॉइस का PDF है{pdf_note_hi}।
- फ़ॉर्मेट संस्करण {version}। कॉलम का विवरण docs/help/DATA_EXPORT_FORMAT.md में है।

वापस Bizboard में लाने के लिए सेटिंग्स -> बैकअप वाला एन्क्रिप्टेड बैकअप इस्तेमाल करें।
"""


def _csv_bom_bytes(rows: list[dict]) -> bytes:
    from core.csv_utils import csv_safe

    buf = io.StringIO()
    if rows:
        fields: list[str] = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: csv_safe(_cell(v)) for k, v in row.items()})
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def _cell(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return "" if value is None else value


def _invoice_pdfs(company) -> tuple[list[tuple[str, bytes]], int]:
    from sales.models import SalesInvoice
    from sales.pdf import render_gst_tax_invoice

    done = SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.COMPLETED).order_by("invoice_date", "pk")
    total = done.count()
    out = []
    try:
        from celery.exceptions import SoftTimeLimitExceeded
    except ImportError:  # pragma: no cover - celery is a hard dependency
        SoftTimeLimitExceeded = ()  # noqa: N806
    for inv in done.select_related("customer", "company")[:MAX_INVOICE_PDFS]:
        try:
            out.append((f"pdf/{inv.number or inv.pk}.pdf", render_gst_tax_invoice(inv)))
        except SoftTimeLimitExceeded:
            raise  # the time limit is not "one bad invoice": stop and mark the export failed
        except Exception:  # noqa: BLE001 - one bad invoice must not lose the whole export
            logger.exception("readable export: invoice %s PDF failed", inv.pk)
    return out, total


def build_readable_zip(company) -> tuple[bytes, dict]:
    """Return the ZIP bytes and its manifest (tests and small companies; the task streams)."""
    buf = io.BytesIO()
    manifest = write_readable_zip(company, buf)
    return buf.getvalue(), manifest


def write_readable_zip(company, fileobj) -> dict:
    """Write the ZIP into ``fileobj`` one file at a time and return its manifest."""
    from .tenant_backup import build_export_payload

    payload = build_export_payload(company)
    files_meta: list[dict] = []
    zf = zipfile.ZipFile(fileobj, "w", compression=zipfile.ZIP_DEFLATED)

    def _add(name: str, data: bytes, rows: int) -> None:
        zf.writestr(name, data)
        files_meta.append({"name": name, "rows": rows, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})

    for section in list(payload):
        rows = payload.pop(section)  # free each section once written
        if section in _SKIP_SECTIONS or not isinstance(rows, list):
            continue
        drop = _DROP_COLUMNS.get(section)
        if drop:
            rows = [{k: v for k, v in row.items() if k not in drop} for row in rows]
        _add(f"{section}.csv", _csv_bom_bytes(rows), len(rows))
    pdfs, total_pdfs = _invoice_pdfs(company)
    more = total_pdfs - len(pdfs)
    pdf_note = f" (the first {len(pdfs)} of {total_pdfs}; ask support for the rest)" if more > 0 else ""
    pdf_note_hi = f" (कुल {total_pdfs} में से पहले {len(pdfs)}; बाकी के लिए सपोर्ट से कहें)" if more > 0 else ""
    readme = (README_EN.format(pdf_note=pdf_note, version=FORMAT_VERSION) + "\n\n"
              + README_HI.format(pdf_note_hi=pdf_note_hi, version=FORMAT_VERSION)).encode("utf-8")
    included = len(pdfs)
    for name, data in pdfs:
        _add(name, data, 1)
    del pdfs
    _add("README.txt", readme, 0)
    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "company": {"id": company.pk, "name": company.name, "gstin": getattr(company, "gstin", "") or ""},
        "generated_at": timezone.now().isoformat(),
        "files": files_meta,
        "invoice_pdfs": {"included": included, "total": total_pdfs},
    }
    zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    zf.close()
    return manifest


def run_export(export_id: int) -> None:
    """Build one requested export (Celery task body)."""
    from core.rls import company_scope

    from .models import ReadableExport

    import tempfile

    from django.core.files import File

    row = ReadableExport.objects.select_related("company").filter(pk=export_id).first()
    if row is None:
        return  # the company was erased meanwhile
    with company_scope(row.company_id):
        fields = ["status", "error", "updated_at"]
        try:
            with tempfile.TemporaryFile() as tmp:  # streamed to disk, not built in memory
                manifest = write_readable_zip(row.company, tmp)
                size = tmp.tell()
                tmp.seek(0)
                path = default_storage.save(f"readable-exports/{row.company_id}/{row.public_id}.zip", File(tmp))
            row.storage_path = path
            row.size = size
            row.manifest = {k: manifest[k] for k in ("format", "format_version", "generated_at", "invoice_pdfs")}
            row.status = ReadableExport.Status.READY
            row.ready_at = timezone.now()
            row.expires_at = row.ready_at + timedelta(hours=LINK_HOURS)
            fields += ["storage_path", "size", "manifest", "ready_at", "expires_at"]
        except BaseException as exc:  # noqa: BLE001 - incl. the soft time limit; recorded on the row
            logger.exception("readable export %s failed", export_id)
            row.status = ReadableExport.Status.FAILED
            row.error = str(exc)[:300] or exc.__class__.__name__
            _save_if_present(row, fields)
            if not isinstance(exc, Exception):
                raise
            return
        # update_fields: an export erased while it was building must not be inserted again.
        _save_if_present(row, fields)


def _save_if_present(row, fields: list[str]) -> None:
    from django.db import DatabaseError

    try:
        row.save(update_fields=fields)
    except DatabaseError:
        logger.warning("readable export %s is gone (company erased?); not saved", row.pk)
        if row.storage_path and default_storage.exists(row.storage_path):
            default_storage.delete(row.storage_path)


def delete_company_files(company_id: int) -> int:
    """Delete every readable-export ZIP of a company (erasure, sandbox teardown). The rows go with
    the company; without this the plaintext ZIPs would outlive the erasure in storage."""
    from core.rls import rls_bypass

    from .models import ReadableExport

    n = 0
    with rls_bypass():
        for path in ReadableExport.objects.filter(company_id=company_id).exclude(storage_path="").values_list(
            "storage_path", flat=True,
        ):
            try:
                if default_storage.exists(path):
                    default_storage.delete(path)
                    n += 1
            except Exception:  # noqa: BLE001 - keep deleting the rest
                logger.exception("could not delete readable export %s", path)
    return n


def purge_expired() -> int:
    """Delete ZIPs whose link ran out (daily). The row stays as the record of the export."""
    from core.rls import rls_bypass

    from .models import ReadableExport

    n = 0
    with rls_bypass():
        for row in ReadableExport.objects.filter(status=ReadableExport.Status.READY, expires_at__lte=timezone.now()):
            if row.storage_path and default_storage.exists(row.storage_path):
                default_storage.delete(row.storage_path)
            row.status = ReadableExport.Status.EXPIRED
            row.save(update_fields=["status", "updated_at"])
            n += 1
        # Builds that died never leave PENDING on their own.
        ReadableExport.objects.filter(
            status=ReadableExport.Status.PENDING,
            created_at__lte=timezone.now() - timedelta(minutes=STALE_PENDING_MINUTES),
        ).update(status=ReadableExport.Status.FAILED, error="The export did not finish. Ask for a new one.")
    return n
