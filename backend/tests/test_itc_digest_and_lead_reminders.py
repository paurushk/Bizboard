"""ITC expiry digest, PO supplier nudge, and lead-activity reminders."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import Notification
from crm.models import Lead, LeadActivity
from crm.tasks import remind_due_lead_activities
from masters.models import Supplier
from payments.dunning import _ist_now
from reporting.ims import send_itc_expiry_digest_for_company, supplier_po_nudge
from reporting.models import Gstr2bIngest


def _quiet_window(company, *, quiet: bool):
    if not quiet:
        company.dunning_quiet_hours_start = 0
        company.dunning_quiet_hours_end = 0
    else:
        hour = _ist_now().hour
        company.dunning_quiet_hours_start = hour
        company.dunning_quiet_hours_end = (hour + 1) % 24 or 1
    company.save(update_fields=["dunning_quiet_hours_start", "dunning_quiet_hours_end"])


@pytest.mark.django_db
def test_itc_digest_sends_once_per_id_set_and_skips_quiet_hours(tenant_a):
    company = tenant_a.company
    _quiet_window(company, quiet=False)
    row = Gstr2bIngest.objects.create(
        company=company,
        period="2025-04",
        supplier_gstin="29AAAAA0000A1ZY",
        invoice_number="ITC-1",
        invoice_date=date(2025, 4, 1),
        taxable_value=Decimal("100"),
        cgst=Decimal("9"),
        sgst=Decimal("9"),
    )
    as_of = date(2026, 11, 10)
    assert send_itc_expiry_digest_for_company(company, as_of=as_of) == "sent"
    note = Notification.objects.get(company=company, subject="ITC expiring — Section 16(4)")
    assert note.channel == Notification.Channel.EMAIL
    assert note.recipient == "owner@alpha.test"
    assert note.body.startswith(f"ids:{row.id}")
    assert "not a filing opinion" in note.body
    assert send_itc_expiry_digest_for_company(company, as_of=as_of) == "skipped"

    _quiet_window(company, quiet=True)
    row.invoice_number = "ITC-2"
    row.save(update_fields=["invoice_number"])
    before = Notification.objects.filter(company=company).count()
    assert send_itc_expiry_digest_for_company(company, as_of=as_of) == "quiet"
    assert Notification.objects.filter(company=company).count() == before


@pytest.mark.django_db
def test_supplier_nudge_distinguishes_missing_history_from_a_score(tenant_a):
    company = tenant_a.company
    known = Supplier.objects.create(company=company, name="Known", gstin="29AAAAA0000A1ZY")
    unknown = Supplier.objects.create(company=company, name="Unknown", gstin="27AAPFU0939F1ZV")
    assert supplier_po_nudge(company, known)["state"] == "no_ims_history"
    Gstr2bIngest.objects.create(
        company=company,
        period="2026-09",
        supplier_gstin="29AAAAA0000A1ZY",
        invoice_number="PO-1",
        invoice_date=date(2026, 9, 1),
        taxable_value=Decimal("10"),
        ims_action=Gstr2bIngest.ImsAction.REJECT,
    )
    scored = supplier_po_nudge(company, known)
    assert scored["state"] == "scored"
    assert scored["period"] == "2026-09"
    assert scored["rejections"] == 1
    assert supplier_po_nudge(company, unknown)["state"] == "no_ims_history"

    resp = tenant_a.client.get(f"/api/v1/reports/gstr2b/supplier-nudge/?supplier={known.id}")
    assert resp.status_code == 200
    assert resp.data["state"] == "scored"


@pytest.mark.django_db
def test_lead_reminder_sends_one_in_app_notice_and_retries_after_quiet_hours(tenant_a):
    company = tenant_a.company
    _quiet_window(company, quiet=False)
    lead = Lead.objects.create(company=company, name="Follow up")
    activity = LeadActivity.objects.create(
        company=company,
        lead=lead,
        kind=LeadActivity.Kind.CALL,
        body="Call them",
        due_at=timezone.now() - timedelta(minutes=5),
    )
    first = remind_due_lead_activities()
    assert first["sent"] == 1
    activity.refresh_from_db()
    assert activity.reminded_at is not None
    note = Notification.objects.get(company=company, channel=Notification.Channel.IN_APP)
    assert note.status == Notification.Status.SENT
    assert note.recipient == "owner@alpha.test"
    second = remind_due_lead_activities()
    assert second["sent"] == 0
    assert Notification.objects.filter(company=company, channel=Notification.Channel.IN_APP).count() == 1

    quiet_lead = Lead.objects.create(company=company, name="Later")
    quiet_activity = LeadActivity.objects.create(
        company=company,
        lead=quiet_lead,
        body="Wait",
        due_at=timezone.now() - timedelta(minutes=1),
    )
    _quiet_window(company, quiet=True)
    quiet = remind_due_lead_activities()
    assert quiet["quiet"] >= 1
    quiet_activity.refresh_from_db()
    assert quiet_activity.reminded_at is None
