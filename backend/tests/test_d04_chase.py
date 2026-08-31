"""D-04: IMS/2B not-in-books chase list, WhatsApp request, photo → import queue."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from reporting.models import Gstr2bIngest
from tests.conftest import make_supplier

pytestmark = pytest.mark.django_db

PERIOD = timezone.localdate().strftime("%Y-%m")

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00"
    b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _enable_gst(tenant):
    tenant.company.gstin = "29ABCDE1234F1ZW"
    tenant.company.state = "Karnataka"
    tenant.company.save(update_fields=["gstin", "state"])


def test_missing_documents_list_has_five_ims_not_in_books(tenant_a):
    _enable_gst(tenant_a)
    make_supplier(tenant_a.company, gstin="29AAAAA0000A1Z5")
    for i in range(5):
        Gstr2bIngest.objects.create(
            company=tenant_a.company,
            period=PERIOD,
            supplier_gstin="29AAAAA0000A1Z5",
            invoice_number=f"IMS-{i+1}",
            invoice_date=date(2026, 8, 10),
            taxable_value=Decimal("1000"),
            cgst=Decimal("90"),
            sgst=Decimal("90"),
            match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
        )
    resp = tenant_a.client.get("/api/v1/reports/gstr2b/missing-documents/", {"period": PERIOD})
    assert resp.status_code == 200, resp.data
    assert resp.data["count"] == 5
    assert len(resp.data["items"]) == 5


def test_photo_reply_lands_in_import_queue(tenant_a):
    _enable_gst(tenant_a)
    row = Gstr2bIngest.objects.create(
        company=tenant_a.company,
        period=PERIOD,
        supplier_gstin="29AAAAA0000A1Z5",
        invoice_number="PHOTO-1",
        invoice_date=date(2026, 8, 10),
        taxable_value=Decimal("500"),
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
        match_class=Gstr2bIngest.MatchClass.MISSING_IN_BOOKS,
    )
    uploaded = SimpleUploadedFile("bill.png", PNG, content_type="image/png")
    resp = tenant_a.client.post(
        f"/api/v1/reports/gstr2b/{row.pk}/chase-photo/",
        {"file": uploaded},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    row.refresh_from_db()
    assert row.chase_status == Gstr2bIngest.ChaseStatus.RECEIVED
    assert row.chase_import_job_id
    from imports.models import ImportJob

    job = ImportJob.objects.get(pk=row.chase_import_job_id)
    assert job.kind == ImportJob.Kind.PURCHASE_BILL
