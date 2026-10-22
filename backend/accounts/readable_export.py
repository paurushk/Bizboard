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

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger(__name__)

FORMAT_NAME = "bizboard-readable-export"
FORMAT_VERSION = "1.0"
LINK_HOURS = 24
MAX_INVOICE_PDFS = 500
_SKIP_SECTIONS = {"company", "file_asset_warnings"}

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
    for inv in done.select_related("customer", "company")[:MAX_INVOICE_PDFS]:
        try:
            out.append((f"pdf/{inv.number or inv.pk}.pdf", render_gst_tax_invoice(inv)))
        except Exception:  # noqa: BLE001 - one bad invoice must not lose the whole export
            logger.exception("readable export: invoice %s PDF failed", inv.pk)
    return out, total


def build_readable_zip(company) -> tuple[bytes, dict]:
    """Return the ZIP bytes and its manifest."""
    from .tenant_backup import build_export_payload

    payload = build_export_payload(company)
    files: list[tuple[str, bytes, int]] = []
    for section, rows in payload.items():
        if section in _SKIP_SECTIONS or not isinstance(rows, list):
            continue
        files.append((f"{section}.csv", _csv_bom_bytes(rows), len(rows)))
    pdfs, total_pdfs = _invoice_pdfs(company)
    more = total_pdfs - len(pdfs)
    pdf_note = f" (the first {len(pdfs)} of {total_pdfs}; ask support for the rest)" if more > 0 else ""
    pdf_note_hi = f" (कुल {total_pdfs} में से पहले {len(pdfs)}; बाकी के लिए सपोर्ट से कहें)" if more > 0 else ""
    readme = (README_EN.format(pdf_note=pdf_note, version=FORMAT_VERSION) + "\n\n"
              + README_HI.format(pdf_note_hi=pdf_note_hi, version=FORMAT_VERSION)).encode("utf-8")
    entries = [*files, *[(name, data, 1) for name, data in pdfs], ("README.txt", readme, 0)]
    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "company": {"id": company.pk, "name": company.name, "gstin": getattr(company, "gstin", "") or ""},
        "generated_at": timezone.now().isoformat(),
        "files": [
            {"name": name, "rows": rows, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data, rows in entries
        ],
        "invoice_pdfs": {"included": len(pdfs), "total": total_pdfs},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for name, data, _rows in entries:
            zf.writestr(name, data)
    return buf.getvalue(), manifest


def run_export(export_id: int) -> None:
    """Build one requested export (Celery task body)."""
    from core.rls import company_scope

    from .models import ReadableExport

    row = ReadableExport.objects.select_related("company").get(pk=export_id)
    with company_scope(row.company_id):
        try:
            data, manifest = build_readable_zip(row.company)
            path = default_storage.save(
                f"readable-exports/{row.company_id}/{row.public_id}.zip", ContentFile(data),
            )
            row.storage_path = path
            row.size = len(data)
            row.manifest = {k: manifest[k] for k in ("format", "format_version", "generated_at", "invoice_pdfs")}
            row.status = ReadableExport.Status.READY
            row.ready_at = timezone.now()
            row.expires_at = row.ready_at + timedelta(hours=LINK_HOURS)
        except Exception as exc:  # noqa: BLE001 - recorded on the row for the owner and support
            logger.exception("readable export %s failed", export_id)
            row.status = ReadableExport.Status.FAILED
            row.error = str(exc)[:300]
        row.save()


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
    return n
