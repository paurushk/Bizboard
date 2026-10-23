"""Regression tests for the deep review of the full-SaaS Phase 1 and 2 build (2026-10-23).

Each test names the defect it pins; the money-path ones for TDS credit and plan changes live next
to their features (test_tds_claims_trial_guard.py, test_plan_change_autopay.py), sessions and
Google sign-in in test_user_sessions_id3.py / test_google_signin_id5.py.
"""

import base64
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings
from django.utils import timezone

from accounts.models import CompanyUser, ReadableExport, User
from billing.models import Subscription
from core.exceptions import BusinessRuleError
from support.models import PlatformTicket, SupportAccessGrant
from support.platform_tickets import open_ticket

pytestmark = pytest.mark.django_db


# --- support access (ID4) ---------------------------------------------------------------------


def _ticket(tenant):
    return open_ticket(company=tenant.company, user=tenant.owner, subject="Stock looks wrong", description="d")


def test_closing_the_request_ends_support_access_at_once(tenant_a):
    from support.access import grant_access, usable_grant

    staff = User.objects.create_user(email="desk@bizboard.example", password="x-Strong-pass-1", is_staff=True)
    ticket = _ticket(tenant_a)
    grant = grant_access(company=tenant_a.company, owner=tenant_a.owner, ticket_id=ticket.pk)
    assert usable_grant(grant.pk, staff) is not None
    resp = tenant_a.client.post(f"/api/v1/support/platform-tickets/{ticket.pk}/resolve/")
    assert resp.status_code == 200, resp.content
    grant.refresh_from_db()
    assert grant.revoked_at is not None and grant.revoke_reason == "ticket_closed"
    assert usable_grant(grant.pk, staff) is None


@pytest.mark.parametrize("hours", [0, "24h", -5, 999])
def test_bad_hours_are_refused_not_widened_to_the_maximum(tenant_a, hours):
    from support.access import grant_access

    with pytest.raises(BusinessRuleError):
        grant_access(company=tenant_a.company, owner=tenant_a.owner, ticket_id=_ticket(tenant_a).pk, hours=hours)


def test_listing_grants_does_not_use_up_the_sensitive_action_budget(tenant_a):
    for _ in range(15):  # sensitive_action is 10/min; the banner reads this on every screen
        assert tenant_a.client.get("/api/v1/support/access-grants/").status_code == 200
    assert tenant_a.client.get("/api/v1/company/export/readable/").status_code == 200


def test_a_lapsed_tenant_can_still_raise_a_support_request(tenant_a):
    sub = Subscription.objects.filter(company=tenant_a.company).first()
    if sub is None:
        from billing.models import Plan

        plan = Plan.objects.create(name="P", slug="p-review", price_paise=1)
        sub = Subscription.objects.create(company=tenant_a.company, plan=plan)
    sub.status = Subscription.Status.SUSPENDED
    sub.save(update_fields=["status"])
    with override_settings(REQUIRE_SUBSCRIPTION=True):
        resp = tenant_a.client.post("/api/v1/support/platform-tickets/", {
            "subject": "Payment failed", "description": "Help", "severity": "P2",
        }, format="json")
    assert resp.status_code == 201, resp.content


def test_staff_can_reply_to_a_ticket_in_admin(client, tenant_a):
    from support.models import PlatformTicketMessage

    admin = User.objects.create_superuser(email="root@bizboard.example", password="x-Strong-pass-1")
    ticket = _ticket(tenant_a)
    client.force_login(admin)
    url = f"/admin/support/platformticket/{ticket.pk}/change/"
    page = client.get(url)
    if page.status_code == 404:
        pytest.skip("Django admin is not mounted in this settings module")
    assert page.status_code == 200
    data = {
        "subject": ticket.subject, "description": ticket.description, "severity": ticket.severity,
        "tag": ticket.tag, "status": ticket.status, "assignee": "",
        "messages-TOTAL_FORMS": "1", "messages-INITIAL_FORMS": "0", "messages-MIN_NUM_FORMS": "0",
        "messages-MAX_NUM_FORMS": "1000", "messages-0-body": "We are looking at it.",
    }
    resp = client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:500]
    assert PlatformTicketMessage.objects.filter(ticket=ticket, from_staff=True, body="We are looking at it.").exists()


def test_deleting_a_company_with_a_support_grant_is_not_blocked(tenant_a):
    from support.access import grant_access

    grant_access(company=tenant_a.company, owner=tenant_a.owner, ticket_id=_ticket(tenant_a).pk)
    PlatformTicket.objects.filter(company=tenant_a.company).delete()  # PROTECT used to refuse this
    assert not SupportAccessGrant.objects.filter(company=tenant_a.company).exists()


# --- readable export (DL1) --------------------------------------------------------------------


def test_a_stale_pending_export_no_longer_blocks_a_new_one(tenant_a):
    row = ReadableExport.objects.create(company=tenant_a.company, requested_by=tenant_a.owner,
                                        created_by=tenant_a.owner, updated_by=tenant_a.owner)
    ReadableExport.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(hours=2))
    with mock.patch("accounts.tasks.build_readable_export_task.delay"):
        resp = tenant_a.client.post("/api/v1/company/export/readable/", {"password": "StrongPass123!"}, format="json")
    assert resp.status_code == 202, resp.content
    row.refresh_from_db()
    assert row.status == ReadableExport.Status.FAILED


def test_a_broker_outage_fails_the_export_instead_of_leaving_it_pending(tenant_a):
    with mock.patch("accounts.tasks.build_readable_export_task.delay", side_effect=RuntimeError("broker down")):
        resp = tenant_a.client.post("/api/v1/company/export/readable/", {"password": "StrongPass123!"}, format="json")
    assert resp.status_code == 202
    assert ReadableExport.objects.get(company=tenant_a.company).status == ReadableExport.Status.FAILED


def test_erasing_a_company_deletes_its_readable_export_files(tenant_a):
    from django.core.files.base import ContentFile

    from accounts.readable_export import delete_company_files

    path = default_storage.save(f"readable-exports/{tenant_a.company.pk}/x.zip", ContentFile(b"PK"))
    ReadableExport.objects.create(company=tenant_a.company, requested_by=tenant_a.owner, storage_path=path,
                                  status=ReadableExport.Status.READY)
    assert delete_company_files(tenant_a.company.pk) == 1
    assert not default_storage.exists(path)


# --- ownership (ID1) --------------------------------------------------------------------------


def test_an_offer_from_an_owner_who_was_demoted_cannot_be_accepted(tenant_a):
    from accounts.ownership import accept_transfer, start_transfer

    co_owner = User.objects.create_user(email="co@alpha.example", password="x-Strong-pass-1")
    CompanyUser.objects.create(company=tenant_a.company, user=co_owner, role=CompanyUser.Role.OWNER)
    _transfer, token = start_transfer(company=tenant_a.company, from_user=co_owner, to_user_id=tenant_a.staff.pk)
    CompanyUser.objects.filter(company=tenant_a.company, user=co_owner).update(role=CompanyUser.Role.VIEWER)
    with pytest.raises(BusinessRuleError, match="no longer an owner"):
        accept_transfer(token=token, user=tenant_a.staff)
    staff_cu = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    assert staff_cu.role != CompanyUser.Role.OWNER
    assert CompanyUser.objects.get(company=tenant_a.company, user=co_owner).role == CompanyUser.Role.VIEWER


def test_offer_to_a_removed_member_is_a_clear_refusal_not_a_500(tenant_a):
    from accounts.ownership import accept_transfer, start_transfer

    _transfer, token = start_transfer(company=tenant_a.company, from_user=tenant_a.owner, to_user_id=tenant_a.staff.pk)
    CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.staff).update(is_active=False)
    with pytest.raises(BusinessRuleError):
        accept_transfer(token=token, user=tenant_a.staff)


def test_rollout_flag_off_is_stored_as_off(tenant_a):
    from accounts.rollout_grants import grantable_keys, set_flag

    admin = User.objects.create_superuser(email="flags@bizboard.example", password="x-Strong-pass-1")
    key = sorted(grantable_keys())[0]
    set_flag(tenant_a.company, key=key, on=False, staff_user=admin, reason="trial hold for pilot")
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags.get(key) is False


# --- imports (GR1a / GR1b) --------------------------------------------------------------------


def test_legacy_advance_is_noted_and_the_totals_still_tie():
    from integrations.legacy_import import parse_legacy_file

    csv = (
        "Name,Group,Mobile No.,GSTIN,State,Op. Bal.,Dr/Cr\n"
        "Asha Traders,Sundry Debtors,9820011111,,Maharashtra,1500.00,Dr\n"
        "Ravi Stores,Sundry Debtors,9820033333,,Maharashtra,300.00,Cr\n"
        "Salary Payable,Provisions,,,,200000.00,Cr\n"
        "Total,,,,,1800.00,Dr\n"
    )
    preview = parse_legacy_file("busy", csv.encode(), "parties.csv")
    assert preview["errors"] == []
    assert [c["name"] for c in preview["customers"]] == ["Asha Traders", "Ravi Stores"]
    assert preview["suppliers"] == []  # "Salary Payable" is not a party
    notes = " ".join(n["warning"] for n in preview["notes"])
    assert "advance" in notes and "Salary Payable" in notes and "Total" in notes


@pytest.mark.parametrize("text,amount,side", [
    ("1,23,456.00", Decimal("123456.00"), ""),
    ("Rs. 1,500.00", Decimal("1500.00"), ""),
    ("(500)", Decimal("-500"), ""),
    ("5,000.00 Cr.", Decimal("5000.00"), "cr"),
])
def test_legacy_balances_are_read_as_one_number(text, amount, side):
    from integrations.legacy_import import _balance

    assert _balance(text) == (amount, side)


def test_legacy_unreadable_balance_is_a_row_error_not_zero():
    from integrations.legacy_import import parse_legacy_file

    csv = "Name,Group,Op. Bal.,Dr/Cr\nAsha Traders,Sundry Debtors,1.500.00 Dr,Dr\n"
    preview = parse_legacy_file("busy", csv.encode(), "parties.csv")
    assert preview["errors"] and preview["errors"][0]["row"] == 2


def test_items_without_a_code_get_a_stable_code_from_their_name():
    from integrations.legacy_import import parse_legacy_file

    one = parse_legacy_file("vyapar", b"Item Name,Sale Price,Opening Stock Quantity\nRice,50,10\n", "a.csv")
    two = parse_legacy_file("vyapar", b"Item Name,Sale Price,Opening Stock Quantity\nSoap,20,5\nRice,50,0\n", "b.csv")
    assert one["products"][0]["sku"] == two["products"][1]["sku"] != two["products"][0]["sku"]


def test_bad_gst_rate_is_a_row_error():
    from integrations.legacy_import import parse_legacy_file

    csv = b"Item Name,Tax Rate,Sale Price,Opening Stock Quantity\nBolt,28% + 12% Cess,6,1\nNut,0.18,2,1\n"
    preview = parse_legacy_file("vyapar", csv, "items.csv")
    assert [p["gst_rate"] for p in preview["products"]] == ["18"]
    assert "Bolt" in preview["errors"][0]["error"]


def test_csv_row_with_extra_cells_is_refused_with_a_reason():
    from integrations.legacy_import import parse_legacy_file

    with pytest.raises(BusinessRuleError, match="more cells"):
        parse_legacy_file("busy", b"Name,Group,Op. Bal.\nAsha Traders, Pune,Sundry Debtors,100\n", "p.csv")


_XML = """<ENVELOPE><BODY><IMPORTDATA><REQUESTDATA>
<TALLYMESSAGE><GROUP NAME="Debtors - Pune"><PARENT>Sundry Debtors</PARENT></GROUP></TALLYMESSAGE>
<TALLYMESSAGE><LEDGER NAME="Mehta &amp; Co"><PARENT>Debtors - Pune</PARENT><OPENINGBALANCE>-5000.00</OPENINGBALANCE>
<LEDGERPHONE>022-26781234 / 26781235</LEDGERPHONE></LEDGER></TALLYMESSAGE>
<TALLYMESSAGE><STOCKITEM NAME="Steel Rod"><HSNCODE>7214 10 10</HSNCODE><OPENINGBALANCE>10 Nos</OPENINGBALANCE>
<GSTDETAILS.LIST><APPLICABLEFROM>20170701</APPLICABLEFROM><STATEWISEDETAILS.LIST>
<RATEDETAILS.LIST><GSTRATEDUTYHEAD>Central Tax</GSTRATEDUTYHEAD><GSTRATE>9</GSTRATE></RATEDETAILS.LIST>
<RATEDETAILS.LIST><GSTRATEDUTYHEAD>State Tax</GSTRATEDUTYHEAD><GSTRATE>9</GSTRATE></RATEDETAILS.LIST>
<RATEDETAILS.LIST><GSTRATEDUTYHEAD>Integrated Tax</GSTRATEDUTYHEAD><GSTRATE>18</GSTRATE></RATEDETAILS.LIST>
</STATEWISEDETAILS.LIST></GSTDETAILS.LIST></STOCKITEM></TALLYMESSAGE>
</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"""


def test_tally_xml_reads_sub_groups_the_integrated_rate_and_cleans_phone_and_hsn():
    from integrations.tally.adapter import parse_tally_masters_csv

    preview = parse_tally_masters_csv(_XML.encode(), "masters.xml")
    assert [c["name"] for c in preview["customers"]] == ["Mehta & Co"]
    assert preview["customers"][0]["phone"] == "02226781234"  # the first number only, digits
    product = preview["products"][0]
    assert product["gst_rate"] == "18" and product["hsn_code"] == "72141010"


# --- core: email webhook, SMS, bot check, metrics ---------------------------------------------


@override_settings(EMAIL_WEBHOOK_USER="hook", EMAIL_WEBHOOK_PASSWORD="secret")
def test_non_ascii_webhook_credentials_are_a_401_not_a_500(client):
    bad = base64.b64encode("é:x".encode()).decode()
    resp = client.post("/api/v1/email/events/", data="{}", content_type="application/json",
                       HTTP_AUTHORIZATION=f"Basic {bad}")
    assert resp.status_code == 401


def test_postmark_auto_replies_are_not_bounces():
    from core.email_webhooks import parse_events

    assert parse_events({"RecordType": "Bounce", "Type": "AutoResponder", "Email": "a@b.in"}) == []
    assert parse_events({"RecordType": "Bounce", "Type": "HardBounce", "Email": "a@b.in"}) == [("a@b.in", "hard_bounce")]
    assert parse_events({"RecordType": "Bounce", "Type": "Blocked", "Email": "a@b.in"}) == [("a@b.in", "soft_bounce")]


def test_a_late_soft_bounce_does_not_lift_a_running_suppression():
    from core.mail import SOFT_LIMIT, is_suppressed, record_event
    from core.models import EmailSuppression

    for _ in range(SOFT_LIMIT):
        record_event("late@b.in", "soft_bounce")
    assert is_suppressed("late@b.in")
    EmailSuppression.objects.update(window_start=timezone.now() - timedelta(days=10))
    record_event("late@b.in", "soft_bounce")
    assert is_suppressed("late@b.in")


def test_settings_define_the_email_webhook_credentials():
    from django.conf import settings

    assert hasattr(settings, "EMAIL_WEBHOOK_USER") and hasattr(settings, "EMAIL_WEBHOOK_PASSWORD")


@override_settings(SMS_PER_PHONE_HOUR=0, SMS_PER_PHONE_DAY=0, SMS_PER_RANGE_HOUR=2, SMS_PLATFORM_DAILY_CAP=0)
def test_bulk_texts_do_not_use_up_the_otp_number_series():
    from django.core.cache import cache

    from core.services import sms_guard

    cache.clear()
    for i in range(2):
        sms_guard.check_and_count(f"+91982000{i:04d}", "payment_reminder")
    with pytest.raises(sms_guard.SmsBlocked):
        sms_guard.check_and_count("+919820008888", "payment_reminder")  # the bulk series budget is used up
    sms_guard.check_and_count("+919820009999", "otp")  # same series, but sign-in codes have their own
    cache.clear()


def test_sms_numbers_are_normalised_once_before_sending():
    from core.services.sms import SmsProvider

    seen = {}

    def fake_guarded(phone, purpose, send):
        seen["phone"] = phone

    with mock.patch("core.services.sms._guarded", side_effect=fake_guarded):
        SmsProvider.send_template("09876543210", "otp", code="123456")
    assert seen["phone"] == "+919876543210"


@override_settings(BOT_CHECK_PROVIDER="turnstile", TURNSTILE_SECRET_KEY="s", TURNSTILE_ALLOWED_HOSTNAMES="app.bizboard.in")
def test_turnstile_token_from_another_hostname_is_refused():
    import io
    import json

    from core.services import bot_check

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    body = json.dumps({"success": True, "hostname": "evil.example"}).encode()
    with mock.patch("urllib.request.urlopen", return_value=_Resp(body)):
        assert bot_check.verify("tok", "203.0.113.5") is False


def test_unknown_bot_check_provider_is_refused_at_boot(monkeypatch):
    import importlib

    from django.core.exceptions import ImproperlyConfigured

    monkeypatch.setenv("BOT_CHECK_PROVIDER", "turnstyle")
    import config.settings as real

    with pytest.raises(ImproperlyConfigured, match="turnstyle"):
        importlib.reload(real)
    monkeypatch.delenv("BOT_CHECK_PROVIDER")
    importlib.reload(real)


def test_onboarding_gstin_step_uses_the_real_status_value(tenant_a):
    from billing.models import TenantActivation

    company = tenant_a.company
    company.gstin_verification_status = "VALID"
    company.save(update_fields=["gstin_verification_status"])
    row = TenantActivation.objects.filter(company=company).first()
    assert row is not None and row.gstin_verified_at is not None


def test_health_skips_sandbox_companies(tenant_a):
    from support.health import _real_companies

    tenant_a.company.is_sandbox = True
    tenant_a.company.save(update_fields=["is_sandbox"])
    assert not _real_companies().filter(pk=tenant_a.company.pk).exists()


def test_public_link_spread_counts_the_client_network_not_the_proxy():
    from core.middleware import PublicLinkMiddleware
    from core.observability import bind_client_ip

    request = mock.Mock()
    request.META = {"REMOTE_ADDR": "10.0.0.2"}  # the proxy
    with override_settings(PUBLIC_LINK_SPREAD_LIMIT=1), mock.patch("core.ops_metrics.bump_event") as bump:
        for ip in ("203.0.113.5", "198.51.100.5"):
            bind_client_ip(ip)
            PublicLinkMiddleware._note_spread("tok-review-0001", request)
        bind_client_ip(None)
    assert any(c.args and c.args[0] == "public_link_spread" for c in bump.call_args_list)


def test_rls_bypass_is_nesting_safe_on_sqlite_too():
    from core.rls import rls_bypass

    with rls_bypass():
        with rls_bypass():
            pass  # no-op off Postgres; on Postgres the inner block must not clear the outer bypass
