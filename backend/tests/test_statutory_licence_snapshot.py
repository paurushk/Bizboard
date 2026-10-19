"""SET-03: licences printed on an invoice are frozen at completion and respect validity."""

from datetime import date, timedelta
from io import BytesIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from pypdf import PdfReader

from accounts.models import CompanyStatutoryLicence
from sales.models import SalesInvoice
from sales.pdf.gst_tax_invoice import render_gst_tax_invoice
from sales.statutory_snapshot import capture_snapshot, licences_to_print, licences_valid_on
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

FSSAI_A = "12345678901234"
FSSAI_B = "98765432109876"


def _licence(company, number=FSSAI_A, **kwargs):
    return CompanyStatutoryLicence.objects.create(
        company=company, licence_type="FSSAI", licence_number=number, **kwargs
    )


def _pdf_text(invoice) -> str:
    reader = PdfReader(BytesIO(render_gst_tax_invoice(invoice)))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _completed_invoice(tenant):
    product = make_product(tenant.company, sku="SNAP-1", hsn_code="1001")
    add_stock(tenant, product, "10")
    customer = make_customer(tenant.company)
    draft = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    return SalesInvoice.objects.get(pk=draft["id"])


def test_valid_on_respects_dates_and_active_flag(tenant_a):
    company = tenant_a.company
    today = timezone.localdate()
    _licence(company, "11111111111111", valid_upto=today - timedelta(days=1))  # expired
    _licence(company, "22222222222222", valid_from=today + timedelta(days=5))  # not yet
    _licence(company, "33333333333333", is_active=False)  # switched off
    ok = _licence(company, "44444444444444", valid_upto=today)  # last day counts
    rows = licences_valid_on(company, today)
    assert [r["number"] for r in rows] == [ok.licence_number]


def test_historical_mode_keeps_a_since_deactivated_licence_with_an_end_date(tenant_a):
    company = tenant_a.company
    past = date(2026, 5, 10)
    _licence(company, "11111111111111", is_active=False, valid_upto=date(2026, 12, 31))
    _licence(company, "22222222222222", is_active=False)  # no end date: no evidence
    assert [r["number"] for r in licences_valid_on(company, past, historical=True)] == ["11111111111111"]
    assert licences_valid_on(company, past) == []


def test_completion_freezes_licences_and_later_edits_do_not_change_the_invoice(tenant_a):
    lic = _licence(tenant_a.company, FSSAI_A)
    invoice = _completed_invoice(tenant_a)
    assert [r["number"] for r in invoice.statutory_licences_snapshot] == [FSSAI_A]
    assert FSSAI_A in _pdf_text(invoice)

    lic.licence_number = FSSAI_B
    lic.save()
    invoice.refresh_from_db()
    text = _pdf_text(invoice)
    assert FSSAI_A in text
    assert FSSAI_B not in text

    lic.is_active = False
    lic.save()
    invoice.refresh_from_db()
    assert FSSAI_A in _pdf_text(invoice)


def test_completion_without_licences_stores_an_empty_snapshot(tenant_a):
    invoice = _completed_invoice(tenant_a)
    assert invoice.statutory_licences_snapshot == []


def test_expired_licence_is_not_printed_or_captured(tenant_a):
    _licence(tenant_a.company, FSSAI_A, valid_upto=timezone.localdate() - timedelta(days=30))
    invoice = _completed_invoice(tenant_a)
    assert invoice.statutory_licences_snapshot == []
    assert FSSAI_A not in _pdf_text(invoice)


def test_uncaptured_invoice_falls_back_to_licences_valid_on_its_date(tenant_a):
    _licence(tenant_a.company, FSSAI_A)
    _licence(tenant_a.company, FSSAI_B, valid_upto=date(2020, 1, 1))
    invoice = _completed_invoice(tenant_a)
    SalesInvoice.objects.filter(pk=invoice.pk).update(statutory_licences_snapshot=None)
    invoice.refresh_from_db()
    assert [r["number"] for r in licences_to_print(invoice)] == [FSSAI_A]


def test_backfill_snapshots_old_invoices_once_and_leaves_updated_at_alone(tenant_a):
    _licence(tenant_a.company, FSSAI_A)
    invoice = _completed_invoice(tenant_a)
    SalesInvoice.objects.filter(pk=invoice.pk).update(statutory_licences_snapshot=None)
    before = SalesInvoice.objects.get(pk=invoice.pk).updated_at

    call_command("backfill_statutory_licence_snapshots", "--dry-run")
    assert SalesInvoice.objects.get(pk=invoice.pk).statutory_licences_snapshot is None

    call_command("backfill_statutory_licence_snapshots", "--company", str(tenant_a.company.pk))
    after = SalesInvoice.objects.get(pk=invoice.pk)
    assert [r["number"] for r in after.statutory_licences_snapshot] == [FSSAI_A]
    assert after.updated_at == before

    # An edit after the backfill must not be picked up on a second run.
    CompanyStatutoryLicence.objects.filter(company=tenant_a.company).update(licence_number=FSSAI_B)
    call_command("backfill_statutory_licence_snapshots")
    assert [r["number"] for r in SalesInvoice.objects.get(pk=invoice.pk).statutory_licences_snapshot] == [FSSAI_A]


def test_backfill_skips_drafts(tenant_a):
    product = make_product(tenant_a.company, sku="SNAP-D", hsn_code="1001")
    draft = create_draft_invoice(
        tenant_a,
        make_customer(tenant_a.company),
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "18"}],
    )
    call_command("backfill_statutory_licence_snapshots")
    assert SalesInvoice.objects.get(pk=draft["id"]).statutory_licences_snapshot is None


def test_capture_snapshot_sets_but_does_not_save(tenant_a):
    _licence(tenant_a.company, FSSAI_A)
    invoice = _completed_invoice(tenant_a)
    SalesInvoice.objects.filter(pk=invoice.pk).update(statutory_licences_snapshot=None)
    invoice.refresh_from_db()
    capture_snapshot(invoice)
    assert invoice.statutory_licences_snapshot
    assert SalesInvoice.objects.get(pk=invoice.pk).statutory_licences_snapshot is None


# ---- locking, renew / replace, premises state, status (SET-03, second half) -------------------

from types import SimpleNamespace  # noqa: E402

from django.test import override_settings  # noqa: E402

from core.exceptions import BusinessRuleError  # noqa: E402
from masters.models import Product  # noqa: E402
from sales.statutory_forms_guard import assert_statutory_licence_present  # noqa: E402

LIC_URL = "/api/v1/company/statutory-licences/"


def test_completion_locks_the_licences_it_prints(tenant_a):
    lic = _licence(tenant_a.company, FSSAI_A)
    unused = _licence(tenant_a.company, FSSAI_B, is_active=False)
    assert lic.locked_at is None
    _completed_invoice(tenant_a)
    lic.refresh_from_db()
    unused.refresh_from_db()
    assert lic.locked_at is not None
    assert unused.locked_at is None


def _locked(company, number=FSSAI_A, **kwargs):
    lic = _licence(company, number, **kwargs)
    lic.locked_at = timezone.now()
    lic.save(update_fields=["locked_at"])
    return lic


def test_locked_licence_identity_cannot_be_edited(tenant_a):
    lic = _locked(tenant_a.company, valid_upto=date(2030, 1, 1))
    r = tenant_a.client.patch(f"{LIC_URL}{lic.id}/", {"licence_number": FSSAI_B}, format="json")
    assert r.status_code == 400, r.data
    r = tenant_a.client.patch(f"{LIC_URL}{lic.id}/", {"valid_from": "2020-01-01"}, format="json")
    assert r.status_code == 400
    r = tenant_a.client.patch(f"{LIC_URL}{lic.id}/", {"valid_upto": "2029-01-01"}, format="json")
    assert r.status_code == 400
    lic.refresh_from_db()
    assert lic.licence_number == FSSAI_A and lic.valid_upto == date(2030, 1, 1)


def test_locked_licence_end_date_cannot_be_extended_in_place(tenant_a):
    lic = _locked(tenant_a.company, valid_upto=date(2030, 1, 1))
    r = tenant_a.client.patch(f"{LIC_URL}{lic.id}/", {"valid_upto": "2032-01-01"}, format="json")
    assert r.status_code == 400, r.data
    lic.refresh_from_db()
    assert lic.valid_upto == date(2030, 1, 1)


def test_renewal_is_a_new_record_with_the_same_number(tenant_a):
    old = _locked(tenant_a.company, FSSAI_A, valid_upto=date(2030, 1, 1))
    r = tenant_a.client.post(
        f"{LIC_URL}{old.id}/replace/", {"valid_upto": "2032-01-01"}, format="json"
    )
    assert r.status_code == 201, r.data
    old.refresh_from_db()
    new = CompanyStatutoryLicence.objects.get(pk=r.data["id"])
    assert new.pk != old.pk
    assert new.licence_number == FSSAI_A and new.valid_upto == date(2032, 1, 1) and new.is_active
    assert old.is_active is False and old.valid_upto == date(2030, 1, 1) and old.locked_at is not None
    # The new record is not locked until an invoice carries it.
    assert new.locked_at is None
    # Only one active record per number.
    assert CompanyStatutoryLicence.objects.filter(
        company=tenant_a.company, licence_number=FSSAI_A, is_active=True
    ).count() == 1


def test_two_active_licences_cannot_share_a_number(tenant_a):
    _licence(tenant_a.company, FSSAI_A)
    r = tenant_a.client.post(
        LIC_URL, {"licence_type": "FSSAI", "licence_number": FSSAI_A}, format="json"
    )
    assert r.status_code == 400, r.data


def test_locked_licence_can_be_deactivated_but_not_deleted(tenant_a):
    lic = _locked(tenant_a.company)
    assert tenant_a.client.patch(f"{LIC_URL}{lic.id}/", {"is_active": False}, format="json").status_code == 200
    assert tenant_a.client.delete(f"{LIC_URL}{lic.id}/").status_code == 400
    assert CompanyStatutoryLicence.objects.filter(pk=lic.pk).exists()


def test_unlocked_licence_is_still_freely_editable_and_deletable(tenant_a):
    lic = _licence(tenant_a.company, FSSAI_A)
    r = tenant_a.client.patch(f"{LIC_URL}{lic.id}/", {"licence_number": FSSAI_B}, format="json")
    assert r.status_code == 200, r.data
    assert tenant_a.client.delete(f"{LIC_URL}{lic.id}/").status_code == 204


def test_replace_with_a_new_number_creates_it_and_switches_the_old_one_off(tenant_a):
    old = _locked(tenant_a.company, FSSAI_A, premises_state="Maharashtra")
    r = tenant_a.client.post(
        f"{LIC_URL}{old.id}/replace/",
        {"licence_number": FSSAI_B, "valid_upto": "2031-03-31"},
        format="json",
    )
    assert r.status_code == 201, r.data
    old.refresh_from_db()
    new = CompanyStatutoryLicence.objects.get(pk=r.data["id"])
    assert old.is_active is False and old.licence_number == FSSAI_A and old.locked_at is not None
    assert new.is_active is True and new.licence_number == FSSAI_B
    assert new.licence_type == "FSSAI" and new.premises_state == "Maharashtra"
    assert new.locked_at is None


def test_replace_refuses_a_no_op_a_bad_number_and_an_inactive_licence(tenant_a):
    old = _locked(tenant_a.company, FSSAI_A, valid_upto=date(2030, 1, 1))
    nothing = tenant_a.client.post(
        f"{LIC_URL}{old.id}/replace/", {"valid_upto": "2030-01-01"}, format="json"
    )
    assert nothing.status_code == 400
    bad = tenant_a.client.post(f"{LIC_URL}{old.id}/replace/", {"licence_number": "123"}, format="json")
    assert bad.status_code == 400
    # A failed replace leaves the old licence exactly as it was.
    old.refresh_from_db()
    assert old.is_active is True
    assert CompanyStatutoryLicence.objects.filter(company=tenant_a.company).count() == 1
    CompanyStatutoryLicence.objects.filter(pk=old.pk).update(is_active=False)
    inactive = tenant_a.client.post(f"{LIC_URL}{old.id}/replace/", {"licence_number": FSSAI_B}, format="json")
    assert inactive.status_code == 400


def test_status_endpoint_reports_enforcement_and_what_needs_attention(tenant_a):
    today = timezone.localdate()
    _licence(tenant_a.company, "11111111111111", valid_upto=today - timedelta(days=2))
    _licence(tenant_a.company, "22222222222222", valid_upto=today + timedelta(days=10))
    _licence(tenant_a.company, "33333333333333")
    with override_settings(ENABLE_ARCH05_STATUTORY_FORMS=False):
        off = tenant_a.client.get(f"{LIC_URL}status/")
    assert off.status_code == 200, off.data
    assert off.data["enforcement"] is False
    assert off.data["expired"] == 1 and off.data["expiring_soon"] == 1 and off.data["active_licences"] == 3
    with override_settings(ENABLE_ARCH05_STATUTORY_FORMS=True):
        assert tenant_a.client.get(f"{LIC_URL}status/").data["enforcement"] is True


def _food_item(company):
    product = make_product(company, sku="FOOD-1", hsn_code="1001")
    Product.objects.filter(pk=product.pk).update(regulated_category=Product.RegulatedCategory.FOOD)
    product.refresh_from_db()
    return SimpleNamespace(product=product, product_id=product.pk)


def _branch_invoice(gstin):
    return SimpleNamespace(company_gstin=SimpleNamespace(gstin=gstin, state=""))


MAHARASHTRA_GSTIN = "27ABCDE1234F1Z5"


@override_settings(ENABLE_ARCH05_STATUTORY_FORMS=True)
def test_guard_wants_a_licence_for_the_branch_state(tenant_a):
    item = _food_item(tenant_a.company)
    _licence(tenant_a.company, FSSAI_A, premises_state="Karnataka")
    with pytest.raises(BusinessRuleError):
        assert_statutory_licence_present(
            tenant_a.company, [item], invoice=_branch_invoice(MAHARASHTRA_GSTIN)
        )
    # Same licence passes when the invoice is from a Karnataka branch.
    assert_statutory_licence_present(
        tenant_a.company, [item], invoice=_branch_invoice("29ABCDE1234F1Z5")
    )


@override_settings(ENABLE_ARCH05_STATUTORY_FORMS=True)
def test_guard_accepts_a_company_wide_licence_and_unknown_states(tenant_a):
    item = _food_item(tenant_a.company)
    lic = _licence(tenant_a.company, FSSAI_A)  # no premises state: covers every branch
    assert_statutory_licence_present(tenant_a.company, [item], invoice=_branch_invoice(MAHARASHTRA_GSTIN))
    CompanyStatutoryLicence.objects.filter(pk=lic.pk).update(premises_state="Karnataka")
    # Branch state unknown (no invoice): no state filtering, as before.
    assert_statutory_licence_present(tenant_a.company, [item])
    # A licence state that is not a recognised state never hides the licence.
    CompanyStatutoryLicence.objects.filter(pk=lic.pk).update(premises_state="Plot 4, Industrial Area")
    assert_statutory_licence_present(tenant_a.company, [item], invoice=_branch_invoice(MAHARASHTRA_GSTIN))


def test_snapshot_only_carries_licences_for_the_branch_state(tenant_a):
    _licence(tenant_a.company, FSSAI_A, premises_state="Maharashtra")
    _licence(tenant_a.company, FSSAI_B, premises_state="Karnataka")
    today = timezone.localdate()
    rows = licences_valid_on(tenant_a.company, today, state_code="27")
    assert [r["number"] for r in rows] == [FSSAI_A]
    assert len(licences_valid_on(tenant_a.company, today)) == 2
