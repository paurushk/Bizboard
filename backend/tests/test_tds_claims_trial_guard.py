"""WP-BL1 (TDS claims on Bizboard's fees) and WP-AB3 (one free trial per business)."""

from decimal import Decimal
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from billing.models import PlatformGstInvoice, SaasTdsClaim, Subscription, TrialFingerprint
from billing.platform_gst import issue_platform_gst_invoice
from billing.services import end_trial_if_repeat, ensure_register_trial
from billing.tds_claims import (
    apply_pending_credits,
    reject,
    request_refund,
    send_form16a_reminders,
    submit_claim,
    verify_claim,
)
from core.exceptions import BusinessRuleError
from core.services.files import FileService

pytestmark = pytest.mark.django_db


def _cert(tenant):
    return FileService.store_upload(
        company=tenant.company,
        uploaded_file=SimpleUploadedFile("16a.pdf", b"%PDF-1.4 form16a", content_type="application/pdf"),
        user=tenant.owner,
    )


def _invoices(tenant, n=2, prefix="pay_t"):
    return [
        issue_platform_gst_invoice(tenant.company, provider="razorpay", capture_id=f"{prefix}{i}", amount="1180")
        for i in range(n)
    ]


# --- WP-BL1 ---------------------------------------------------------------------------------


def test_claim_amount_is_computed_from_taxable_value_and_cannot_be_typed(tenant_a):
    invs = _invoices(tenant_a)
    claim = submit_claim(
        company=tenant_a.company, user=tenant_a.owner, invoice_ids=[i.pk for i in invs],
        section_code="194J-2", certificate_id=_cert(tenant_a).pk,
    )
    assert claim.taxable_total == Decimal("2000.00")
    assert claim.amount == Decimal("40.00")
    assert claim.status == SaasTdsClaim.Status.SUBMITTED
    assert claim.quarter.endswith(("Q1", "Q2", "Q3", "Q4"))


def test_same_invoice_cannot_be_claimed_twice_unless_rejected(tenant_a):
    inv = _invoices(tenant_a, 1)
    cert = _cert(tenant_a).pk
    first = submit_claim(company=tenant_a.company, user=tenant_a.owner, invoice_ids=[inv[0].pk],
                         section_code="194J-2", certificate_id=cert)
    with pytest.raises(BusinessRuleError, match="already claimed"):
        submit_claim(company=tenant_a.company, user=tenant_a.owner, invoice_ids=[inv[0].pk],
                     section_code="194J-2", certificate_id=cert)
    reject(first, staff_user=tenant_a.owner, reason="Wrong PAN on certificate")
    submit_claim(company=tenant_a.company, user=tenant_a.owner, invoice_ids=[inv[0].pk],
                 section_code="194J-2", certificate_id=cert)


def test_other_companies_invoices_and_unknown_sections_are_refused(tenant_a, tenant_b):
    theirs = _invoices(tenant_b, 1)
    with pytest.raises(BusinessRuleError, match="not yours"):
        submit_claim(company=tenant_a.company, user=tenant_a.owner, invoice_ids=[theirs[0].pk],
                     section_code="194J-2", certificate_id=_cert(tenant_a).pk)
    with pytest.raises(BusinessRuleError, match="section"):
        submit_claim(company=tenant_a.company, user=tenant_a.owner, invoice_ids=[theirs[0].pk],
                     section_code="999X", certificate_id=_cert(tenant_a).pk)


def test_verify_refunds_each_invoice_once_and_the_parts_add_up(tenant_a):
    invs = _invoices(tenant_a, 3)
    claim = submit_claim(company=tenant_a.company, user=tenant_a.owner, invoice_ids=[i.pk for i in invs],
                         section_code="194J-10", certificate_id=_cert(tenant_a).pk, settle_by="REFUND")
    with mock.patch("billing.services.razorpay_refund", side_effect=["rfnd_a", "rfnd_b", "rfnd_c"]) as refund:
        verify_claim(claim, staff_user=tenant_a.owner)
    assert refund.call_count == 3
    assert sum(c.args[1] for c in refund.call_args_list) == int(claim.amount * 100)
    claim.refresh_from_db()
    assert claim.status == SaasTdsClaim.Status.SETTLED
    assert [r["refund"] for r in claim.refund_ids] == ["rfnd_a", "rfnd_b", "rfnd_c"]
    # A TDS refund is not a price reduction: no GST credit note.
    assert not PlatformGstInvoice.objects.filter(kind=PlatformGstInvoice.Kind.CREDIT_NOTE).exists()


def test_a_failed_refund_can_be_retried_without_refunding_twice(tenant_a):
    invs = _invoices(tenant_a, 2)
    claim = submit_claim(company=tenant_a.company, user=tenant_a.owner, invoice_ids=[i.pk for i in invs],
                         section_code="194J-2", certificate_id=_cert(tenant_a).pk, settle_by="REFUND")
    with mock.patch("billing.services.razorpay_refund", side_effect=["rfnd_1", BusinessRuleError("gateway down")]):
        with pytest.raises(BusinessRuleError):
            verify_claim(claim, staff_user=tenant_a.owner)
    claim.refresh_from_db()
    assert claim.status == SaasTdsClaim.Status.VERIFIED and len(claim.refund_ids) == 1
    with mock.patch("billing.services.razorpay_refund", return_value="rfnd_2") as refund:
        verify_claim(claim, staff_user=tenant_a.owner)
    assert refund.call_count == 1
    claim.refresh_from_db()
    assert claim.status == SaasTdsClaim.Status.SETTLED


def test_owner_endpoint_lists_sections_and_submits(tenant_a):
    invs = _invoices(tenant_a, 1)
    resp = tenant_a.client.get("/api/v1/billing/tds-claims/")
    assert resp.status_code == 200
    assert any(s["code"] == "194J-2" for s in resp.json()["data"]["sections"])
    created = tenant_a.client.post(
        "/api/v1/billing/tds-claims/",
        {"invoice_ids": [invs[0].pk], "section": "194C-1", "certificate_id": _cert(tenant_a).pk},
        format="json",
    )
    assert created.status_code == 201, created.content
    assert created.json()["data"]["amount"] in ("10.00", 10.0, "10")


def _verified_credit_claim(tenant, n=2, section="194J-10", prefix="pay_t"):
    invs = _invoices(tenant, n, prefix)
    claim = submit_claim(company=tenant.company, user=tenant.owner, invoice_ids=[i.pk for i in invs],
                         section_code=section, certificate_id=_cert(tenant).pk)
    assert claim.settle_by == SaasTdsClaim.SettleBy.CREDIT  # Q5 default
    with mock.patch("billing.services.razorpay_refund") as refund:
        verify_claim(claim, staff_user=tenant.owner)
    refund.assert_not_called()  # credit waits for the next renewal
    claim.refresh_from_db()
    assert claim.status == SaasTdsClaim.Status.VERIFIED and claim.credit_remaining == claim.amount
    return claim


def test_credit_comes_off_the_next_renewal_by_refunding_part_of_it(tenant_a):
    from billing.views import _invoice_charge

    claim = _verified_credit_claim(tenant_a)  # 2 x 1000 taxable at 10% = 200
    with mock.patch("billing.services.razorpay_refund", return_value="rfnd_cr1") as refund:
        _invoice_charge(tenant_a.company, {"payment_id": "pay_renew1", "amount": Decimal("1180")})
    renewal = PlatformGstInvoice.objects.get(capture_id="pay_renew1")
    refund.assert_called_once()
    assert refund.call_args.args == ("pay_renew1", 20000)
    claim.refresh_from_db()
    assert claim.status == SaasTdsClaim.Status.SETTLED and claim.credit_remaining == 0
    assert claim.credit_applied == [{"invoice": renewal.pk, "refund": "rfnd_cr1", "amount": "200.00"}]
    # A webhook redelivery or the daily task never applies it twice.
    with mock.patch("billing.services.razorpay_refund") as again:
        _invoice_charge(tenant_a.company, {"payment_id": "pay_renew1", "amount": Decimal("1180")})
        apply_pending_credits()
    again.assert_not_called()


def test_credit_larger_than_a_renewal_spreads_over_renewals(tenant_a):
    from billing.views import _invoice_charge

    claim = _verified_credit_claim(tenant_a, n=3)  # 300 credit
    with mock.patch("billing.services.razorpay_refund", side_effect=["r1", "r2"]) as refund:
        _invoice_charge(tenant_a.company, {"payment_id": "pay_small1", "amount": Decimal("118")})
        _invoice_charge(tenant_a.company, {"payment_id": "pay_small2", "amount": Decimal("1180")})
    assert [c.args[1] for c in refund.call_args_list] == [11800, 18200]
    claim.refresh_from_db()
    assert claim.status == SaasTdsClaim.Status.SETTLED


def test_failed_credit_on_the_webhook_is_applied_by_the_daily_task(tenant_a):
    from billing.views import _invoice_charge

    claim = _verified_credit_claim(tenant_a)
    with mock.patch("billing.services.razorpay_refund", side_effect=BusinessRuleError("gateway down")):
        _invoice_charge(tenant_a.company, {"payment_id": "pay_renew2", "amount": Decimal("1180")})
    assert PlatformGstInvoice.objects.filter(capture_id="pay_renew2").exists()  # invoice still issued
    with mock.patch("billing.services.razorpay_refund", return_value="rfnd_late") as refund:
        assert apply_pending_credits() == 1
    refund.assert_called_once()
    claim.refresh_from_db()
    assert claim.status == SaasTdsClaim.Status.SETTLED


@override_settings(RAZORPAY_KEY_ID="rzp_k", RAZORPAY_KEY_SECRET="rzp_s")
def test_owner_can_take_the_remaining_credit_as_a_refund(tenant_a):
    claim = _verified_credit_claim(tenant_a)
    with mock.patch("billing.services.razorpay_refund", side_effect=["ra", "rb"]) as refund:
        resp = tenant_a.client.post(f"/api/v1/billing/tds-claims/{claim.pk}/refund/", format="json")
    assert resp.status_code == 200, resp.content
    assert sum(c.args[1] for c in refund.call_args_list) == 20000
    claim.refresh_from_db()
    assert claim.status == SaasTdsClaim.Status.SETTLED and claim.settle_by == SaasTdsClaim.SettleBy.REFUND
    with pytest.raises(BusinessRuleError, match="closed"):
        request_refund(claim, user=tenant_a.owner)


@override_settings(RAZORPAY_KEY_ID="rzp_k", RAZORPAY_KEY_SECRET="rzp_s")
def test_refund_requested_before_the_check_is_refunded_when_staff_verify(tenant_a):
    invs = _invoices(tenant_a, 1)
    claim = submit_claim(company=tenant_a.company, user=tenant_a.owner, invoice_ids=[invs[0].pk],
                         section_code="194J-2", certificate_id=_cert(tenant_a).pk)
    request_refund(claim, user=tenant_a.owner)
    with mock.patch("billing.services.razorpay_refund", return_value="r") as refund:
        verify_claim(SaasTdsClaim.objects.get(pk=claim.pk), staff_user=tenant_a.owner)
    refund.assert_called_once()


def test_an_accepted_claim_cannot_be_rejected(tenant_a):
    claim = _verified_credit_claim(tenant_a)
    with pytest.raises(BusinessRuleError, match="accepted"):
        reject(claim, staff_user=tenant_a.owner, reason="late")


def test_a_failed_second_credit_keeps_the_first_refund_recorded(tenant_a):
    """Review fix: each claim's credit commits on its own. A gateway error on the second claim must
    not roll back the record of the first refund (which already left Razorpay), or the daily task
    would refund it again."""
    from billing.views import _invoice_charge

    first = _verified_credit_claim(tenant_a, n=1, prefix="pay_first")  # 1000 taxable at 10% = 100
    second = _verified_credit_claim(tenant_a, n=1, prefix="pay_second")
    with mock.patch("billing.services.razorpay_refund", side_effect=["r_first", BusinessRuleError("down")]):
        _invoice_charge(tenant_a.company, {"payment_id": "pay_two", "amount": Decimal("1180")})
    renewal = PlatformGstInvoice.objects.get(capture_id="pay_two")
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == SaasTdsClaim.Status.SETTLED
    assert first.credit_applied == [{"invoice": renewal.pk, "refund": "r_first", "amount": "100.00"}]
    assert second.status == SaasTdsClaim.Status.VERIFIED and second.credit_applied == []
    with mock.patch("billing.services.razorpay_refund", return_value="r_second") as again:
        apply_pending_credits()
    assert [c.args[1] for c in again.call_args_list] == [10000]  # only the second claim, once
    assert again.call_args.kwargs["idempotency_key"] == f"tds-credit-{second.pk}-{renewal.pk}"


@override_settings(RAZORPAY_KEY_ID="rzp_k", RAZORPAY_KEY_SECRET="rzp_s")
def test_refund_request_after_a_settled_refund_does_not_refund_again(tenant_a):
    """Review fix: a second refund request (another tab) re-reads the claim under its lock and
    finds every invoice already refunded."""
    claim = _verified_credit_claim(tenant_a)
    with mock.patch("billing.services.razorpay_refund", side_effect=["ra", "rb"]):
        request_refund(claim, user=tenant_a.owner)
    stale = SaasTdsClaim.objects.get(pk=claim.pk)
    stale.status = SaasTdsClaim.Status.VERIFIED  # what a request that read the row earlier saw
    with mock.patch("billing.services.razorpay_refund") as again:
        from billing.tds_claims import _refund_to_claimed_invoices

        _refund_to_claimed_invoices(stale.pk)
    again.assert_not_called()


def test_refund_switch_is_refused_when_no_refund_is_possible(tenant_a):
    """Review fix: without Razorpay keys (or for a non-Razorpay invoice) the owner's switch to a
    refund is refused before anything changes, so the claim keeps coming off renewals."""
    claim = _verified_credit_claim(tenant_a)
    with pytest.raises(BusinessRuleError):
        request_refund(claim, user=tenant_a.owner)
    claim.refresh_from_db()
    assert claim.settle_by == SaasTdsClaim.SettleBy.CREDIT and claim.status == SaasTdsClaim.Status.VERIFIED


def test_claim_post_with_bad_ids_is_a_400_not_a_500(tenant_a):
    resp = tenant_a.client.post("/api/v1/billing/tds-claims/", {
        "invoice_ids": "12", "section": "194J-2", "certificate_id": "abc",
    }, format="json")
    assert resp.status_code == 400, resp.content


def test_form16a_reminder_once_per_quarter_only_for_unclaimed_gstin_invoices(tenant_a):
    import datetime as dt

    from core.models import Notification

    tenant_a.company.email = "owner@a.example"
    tenant_a.company.save(update_fields=["email"])
    inv = _invoices(tenant_a, 1)[0]
    PlatformGstInvoice.objects.filter(pk=inv.pk).update(
        buyer_gstin="27AAAPL1234C1ZE",
        created_at=timezone.make_aware(dt.datetime(2026, 8, 5, 12)),
    )
    assert send_form16a_reminders(dt.date(2026, 11, 15)) == 0  # not the 16th
    assert send_form16a_reminders(dt.date(2026, 11, 16)) == 1  # Q2 (Jul–Sep)
    assert send_form16a_reminders(dt.date(2026, 11, 16)) == 0  # once
    assert Notification.objects.filter(subject="Claim back TDS for 2026-27 Q2").count() == 1
    assert send_form16a_reminders(dt.date(2027, 2, 16)) == 0  # nothing in Q3


# --- WP-AB3 ---------------------------------------------------------------------------------


def _fresh_company(tenant, *, gstin="", phone="", email=""):
    company = tenant.company
    Subscription.objects.filter(company=company).delete()
    company.gstin, company.phone, company.email = gstin, phone, email
    company.save(update_fields=["gstin", "phone", "email"])
    return company


@override_settings(TRIAL_FINGERPRINT_PEPPER="pep-new,pep-old")
def test_same_gstin_or_same_phone_and_email_gets_no_second_trial(tenant_a, tenant_b):
    first = _fresh_company(tenant_a, gstin="27AAAPL1234C1Z5", phone="9820012345", email="o@alpha.test")
    sub_a = ensure_register_trial(first)
    assert sub_a.trial_ends_at > timezone.now()
    assert not TrialFingerprint.objects.filter(digest__contains="27AAAPL").exists()  # hashed only

    second = _fresh_company(tenant_b, gstin="27AAAPL1234C1Z5")
    sub_b = ensure_register_trial(second)
    assert sub_b.trial_ends_at <= timezone.now() and sub_b.churn_reason == "TRIAL_ALREADY_USED"
    assert sub_b.is_write_blocked()


@override_settings(TRIAL_FINGERPRINT_PEPPER="pep")
def test_phone_alone_is_not_enough_but_phone_and_email_are(tenant_a, tenant_b):
    ensure_register_trial(_fresh_company(tenant_a, phone="9820012345", email="o@alpha.test"))
    only_phone = ensure_register_trial(_fresh_company(tenant_b, phone="+919820012345", email="new@beta.test"))
    assert only_phone.trial_ends_at > timezone.now()
    both = ensure_register_trial(_fresh_company(tenant_b, phone="9820012345", email="O@Alpha.test"))
    assert both.trial_ends_at <= timezone.now()


def test_pepper_rotation_still_matches_old_fingerprints(tenant_a, tenant_b):
    with override_settings(TRIAL_FINGERPRINT_PEPPER="pep-old"):
        ensure_register_trial(_fresh_company(tenant_a, gstin="27AAAPL1234C1Z5"))
    with override_settings(TRIAL_FINGERPRINT_PEPPER="pep-new,pep-old"):
        sub = ensure_register_trial(_fresh_company(tenant_b, gstin="27AAAPL1234C1Z5"))
    assert sub.trial_ends_at <= timezone.now()


def test_fingerprints_older_than_the_window_do_not_count(tenant_a, tenant_b):
    ensure_register_trial(_fresh_company(tenant_a, gstin="27AAAPL1234C1Z5"))
    TrialFingerprint.objects.update(created_at=timezone.now() - timezone.timedelta(days=366))
    sub = ensure_register_trial(_fresh_company(tenant_b, gstin="27AAAPL1234C1Z5"))
    assert sub.trial_ends_at > timezone.now()


def test_gstin_added_in_setup_ends_a_running_repeat_trial(tenant_a, tenant_b):
    ensure_register_trial(_fresh_company(tenant_a, gstin="27AAAPL1234C1Z5"))
    second = _fresh_company(tenant_b)
    sub = ensure_register_trial(second)
    assert sub.trial_ends_at > timezone.now()
    second.gstin = "27AAAPL1234C1Z5"
    second.save(update_fields=["gstin"])
    assert end_trial_if_repeat(second) is True
    sub.refresh_from_db()
    assert sub.trial_ends_at <= timezone.now()


def test_disposable_email_is_refused_at_sign_up(client):
    from billing.trial_guard import disposable_email

    assert disposable_email("someone@mailinator.com")
    assert not disposable_email("owner@alphatraders.in")
    resp = client.post(
        "/api/v1/auth/register/",
        {"email": "x@mailinator.com", "password": "Strong-Pass-123", "company_name": "Temp Co", "accept_terms": True},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "temporary inbox" in resp.content.decode()


def test_tds_claim_refund_is_company_scoped(tenant_a, tenant_b):
    claim = _verified_credit_claim(tenant_a)
    with mock.patch("billing.services.razorpay_refund") as refund:
        resp = tenant_b.client.post(f"/api/v1/billing/tds-claims/{claim.pk}/refund/", format="json")
    assert resp.status_code == 404
    refund.assert_not_called()
