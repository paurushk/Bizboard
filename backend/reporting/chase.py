"""D-04 — missing IMS/2B documents chase (not in books)."""


from core.exceptions import BusinessRuleError
from core.services.whatsapp import _normalize_phone, _wa_me_link
from reporting.ims import classify_and_match
from reporting.models import Gstr2bIngest


def list_missing_documents(company, period: str, *, persist=True):
    classify_and_match(company, period, persist=persist)
    rows = (
        Gstr2bIngest.objects.filter(company=company, period=period)
        .filter(purchase_invoice_id__isnull=True)
        .exclude(match_class=Gstr2bIngest.MatchClass.EXACT)
    )
    missing = []
    for row in rows:
        klass = row.match_class or ""
        if klass == Gstr2bIngest.MatchClass.MISSING_IN_BOOKS or (
            not klass and row.match_status != Gstr2bIngest.MatchStatus.MATCHED
        ):
            if row.chase_status == Gstr2bIngest.ChaseStatus.MATCHED:
                continue
            missing.append(row)
    return missing


def serialize_chase_row(row: Gstr2bIngest) -> dict:
    return {
        "id": row.pk,
        "period": row.period,
        "supplier_gstin": row.supplier_gstin,
        "invoice_number": row.invoice_number,
        "invoice_date": row.invoice_date.isoformat() if row.invoice_date else None,
        "taxable_value": str(row.taxable_value),
        "cgst": str(row.cgst),
        "sgst": str(row.sgst),
        "igst": str(row.igst),
        "status": row.chase_status or Gstr2bIngest.ChaseStatus.NONE,
        "import_job_id": row.chase_import_job_id,
    }


def request_whatsapp(company, period: str, *, user=None, phone: str = "") -> dict:
    rows = list_missing_documents(company, period)
    if not rows:
        raise BusinessRuleError("No missing documents for this period.")
    lines = [
        f"{r.supplier_gstin} {r.invoice_number} {r.taxable_value}".strip()
        for r in rows
    ]
    text = (
        "Please share these purchase bills that are in IMS/GSTR-2B but not in books:\n"
        + "\n".join(lines[:40])
    )
    dest = _normalize_phone(phone) or _normalize_phone(getattr(user, "phone", "") or "")
    if not dest:
        raise BusinessRuleError("No destination phone number for WhatsApp chase.")
    share_link = _wa_me_link(phone=dest, text=text)
    return {
        "count": len(rows),
        "share_link": share_link,
        "mode": "link",
        "status_updated": False,
        "items": [serialize_chase_row(r) for r in rows],
    }


def attach_photo_reply(company, ingest_id: int, uploaded_file, *, user=None) -> dict:
    try:
        row = Gstr2bIngest.objects.get(pk=ingest_id, company=company)
    except Gstr2bIngest.DoesNotExist as exc:
        raise BusinessRuleError("Unknown missing document.") from exc
    from core.models import FileAsset
    from core.services.files import FileService
    from imports.models import ImportJob
    from imports.services import BillImportService

    asset = FileService.store_upload(
        company=company, uploaded_file=uploaded_file, kind=FileAsset.Kind.IMPORT, user=user,
    )
    job = ImportJob.objects.create(
        company=company,
        kind=ImportJob.Kind.PURCHASE_BILL,
        file=asset,
        created_by=user,
        updated_by=user,
    )
    try:
        BillImportService.start_extraction(job)
    except Exception:
        job.refresh_from_db()
        if job.status != ImportJob.Status.FAILED:
            job.status = ImportJob.Status.FAILED
            job.save(update_fields=["status", "updated_at"])
        row.chase_status = Gstr2bIngest.ChaseStatus.REQUESTED
        row.chase_import_job_id = job.pk
        row.save(update_fields=["chase_status", "chase_import_job_id", "updated_at"])
        return {
            "id": row.pk,
            "status": row.chase_status,
            "import_job_id": job.pk,
            "import_status": job.status,
            "error": "extraction_failed",
        }
    job.refresh_from_db()
    row.chase_status = Gstr2bIngest.ChaseStatus.RECEIVED
    row.chase_import_job_id = job.pk
    row.save(update_fields=["chase_status", "chase_import_job_id", "updated_at"])
    return {
        "id": row.pk,
        "status": row.chase_status,
        "import_job_id": job.pk,
        "import_status": job.status,
    }
