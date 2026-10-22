"""WP-ID1 ownership, WP-PO3 platform tickets, WP-CM1 email suppression, WP-SC2 break-glass,
WP-CP2 privacy register, WP-PO2 tenant health."""

import base64
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CompanyUser, OwnershipTransfer, User
from accounts.ownership import (
    accept_transfer,
    approve_recovery,
    complete_due_recoveries,
    request_recovery,
    start_transfer,
)
from core.exceptions import BusinessRuleError

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


def _member(tenant, email, role=CompanyUser.Role.MANAGER):
    user = User.objects.create_user(email=email, password="Member-Pass-123")
    CompanyUser.objects.create(company=tenant.company, user=user, role=role)
    return user


def _staff(email):
    return User.objects.create_user(email=email, password="Staff-Pass-123", is_staff=True)


# --- WP-ID1 ---------------------------------------------------------------------------------


def test_owner_transfer_swaps_roles_and_keeps_one_owner(tenant_a):
    new = _member(tenant_a, "next-owner@alpha.test")
    transfer, token = start_transfer(company=tenant_a.company, from_user=tenant_a.owner, to_user_id=new.pk)
    assert transfer.token_hash and token not in transfer.token_hash
    with pytest.raises(BusinessRuleError, match="not for you"):
        accept_transfer(token=token, user=tenant_a.owner)
    accept_transfer(token=token, user=new)
    roles = dict(CompanyUser.objects.filter(company=tenant_a.company).values_list("user__email", "role"))
    assert roles["next-owner@alpha.test"] == "OWNER"
    assert roles[tenant_a.owner.email] == "MANAGER"
    with pytest.raises(BusinessRuleError, match="expired or was cancelled"):
        accept_transfer(token=token, user=new)


def test_expired_transfer_link_is_refused(tenant_a):
    new = _member(tenant_a, "late@alpha.test")
    transfer, token = start_transfer(company=tenant_a.company, from_user=tenant_a.owner, to_user_id=new.pk)
    OwnershipTransfer.objects.filter(pk=transfer.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(BusinessRuleError, match="expired"):
        accept_transfer(token=token, user=new)


def test_transfer_api_needs_password_and_owner(tenant_a):
    new = _member(tenant_a, "api-next@alpha.test")
    bad = tenant_a.client.post("/api/v1/company/ownership/transfer/",
                               {"to_user_id": new.pk, "password": "wrong"}, format="json")
    assert bad.status_code == 400
    tenant_a.owner.set_password("Owner-Pass-123")
    tenant_a.owner.save()
    ok = tenant_a.client.post("/api/v1/company/ownership/transfer/",
                              {"to_user_id": new.pk, "password": "Owner-Pass-123"}, format="json")
    assert ok.status_code == 201, ok.content
    token = ok.json()["data"]["token"]
    client = APIClient()
    client.force_authenticate(user=new)
    accepted = client.post("/api/v1/company/ownership/accept/", {"token": token}, format="json")
    assert accepted.status_code == 200, accepted.content
    assert CompanyUser.objects.get(company=tenant_a.company, user=new).role == "OWNER"


def test_last_owner_still_cannot_be_demoted(tenant_a):
    cu = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.owner)
    resp = tenant_a.client.patch(f"/api/v1/company/users/{cu.pk}/", {"role": "MANAGER"}, format="json")
    assert resp.status_code == 400
    assert "last active Owner" in resp.content.decode()


def test_staff_recovery_needs_two_staff_and_a_wait(tenant_a):
    from support.platform_tickets import open_ticket

    ticket = open_ticket(company=tenant_a.company, user=tenant_a.owner, subject="Owner lost phone",
                         description="", severity="P1")
    first, second = _staff("s1@bizboard.test"), _staff("s2@bizboard.test")
    t = request_recovery(company=tenant_a.company, staff_user=first, ticket=ticket,
                         recovery_email="director@alpha.test", proof_note="GST portal email matches",
                         reason="Owner lost phone and codes")
    with pytest.raises(BusinessRuleError, match="different staff"):
        approve_recovery(t, staff_user=first)
    approve_recovery(t, staff_user=second)
    assert complete_due_recoveries() == 0  # still inside the 72-hour wait
    with mock.patch("accounts.ownership._email") as email:
        done = complete_due_recoveries(now=timezone.now() + timedelta(hours=73))
    assert done == 1
    assert any("director@alpha.test" == c.args[0] for c in email.call_args_list)
    m = CompanyUser.objects.get(company=tenant_a.company, user__email="director@alpha.test")
    assert m.role == "OWNER" and m.is_active is False  # active once they accept the invite


# --- WP-PO3 ---------------------------------------------------------------------------------


def test_any_member_of_a_trial_company_can_ask_for_help(tenant_a):
    viewer = _member(tenant_a, "viewer@alpha.test", role=CompanyUser.Role.VIEWER)
    client = APIClient()
    client.force_authenticate(user=viewer)
    resp = client.post("/api/v1/support/platform-tickets/", {
        "subject": "Cannot print invoice", "description": "Blank page", "severity": "P2",
        "support_id": "SUP-123", "route": "/sales/invoices/9", "error_codes": ["PDF_FAILED", "bad code!"],
    }, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()["data"]
    assert body["errorCodes"] == ["PDF_FAILED"]
    assert body["slaDueAt"]
    # The owner sees it; another viewer does not.
    assert len(tenant_a.client.get("/api/v1/support/platform-tickets/").json()["data"]) == 1
    other = _member(tenant_a, "viewer2@alpha.test", role=CompanyUser.Role.VIEWER)
    c2 = APIClient()
    c2.force_authenticate(user=other)
    assert c2.get("/api/v1/support/platform-tickets/").json()["data"] == []


def test_tickets_never_cross_companies(tenant_a, tenant_b):
    from support.platform_tickets import open_ticket

    t = open_ticket(company=tenant_b.company, user=tenant_b.owner, subject="B only", description="")
    assert tenant_a.client.get(f"/api/v1/support/platform-tickets/{t.pk}/").status_code == 404
    assert tenant_a.client.post(f"/api/v1/support/platform-tickets/{t.pk}/reply/", {"body": "x"},
                                format="json").status_code == 404
    assert tenant_a.client.post(f"/api/v1/support/platform-tickets/{t.pk}/resolve/").status_code == 404


def test_staff_reply_emails_the_person_who_asked(tenant_a):
    from support.platform_tickets import add_message, open_ticket

    t = open_ticket(company=tenant_a.company, user=tenant_a.owner, subject="Help", description="")
    with mock.patch("core.services.notifications.NotificationService.send") as send:
        add_message(t, author=_staff("agent@bizboard.test"), body="Try again now", from_staff=True)
    assert send.call_args.kwargs["recipient"] == tenant_a.owner.email
    t.refresh_from_db()
    assert t.status == "WAITING_CUSTOMER" and t.first_response_at is not None


# --- WP-CM1 ---------------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_hard_bounce_and_complaint_suppress_and_soft_bounces_suppress_after_three():
    from core.mail import Suppressed, is_suppressed, record_event, send

    record_event("hard@x.in", "hard_bounce")
    assert is_suppressed("HARD@x.in")
    with pytest.raises(Suppressed):
        send(subject="s", body="b", to="hard@x.in")
    for _ in range(2):
        record_event("soft@x.in", "soft_bounce")
    assert not is_suppressed("soft@x.in")
    record_event("soft@x.in", "soft_bounce")
    assert is_suppressed("soft@x.in")
    assert len(mail.outbox) == 0


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FRONTEND_URL="https://app.test")
def test_only_optional_mail_gets_unsubscribe_headers_and_honours_opt_out(client):
    from core.mail import send

    send(subject="Invoice", body="b", to="a@x.in", category="transactional")
    send(subject="Tips", body="b", to="a@x.in", category="product")
    assert "List-Unsubscribe" not in mail.outbox[0].extra_headers
    headers = mail.outbox[1].extra_headers
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    url = headers["List-Unsubscribe"].strip("<>").replace("https://app.test", "")
    assert client.post(url).status_code == 200
    assert send(subject="Tips", body="b", to="a@x.in", category="product") is False
    assert send(subject="Invoice", body="b", to="a@x.in", category="transactional") is True
    assert client.get(url.replace("c=product", "c=marketing")).status_code == 400


@override_settings(EMAIL_WEBHOOK_USER="hook", EMAIL_WEBHOOK_PASSWORD="pw")
def test_webhook_needs_credentials_and_reads_ses_and_postmark():
    from core.mail import is_suppressed

    auth = "Basic " + base64.b64encode(b"hook:pw").decode()
    c = APIClient()
    assert c.post("/api/v1/email/events/", {}, format="json").status_code == 401
    ses = {"Type": "Notification", "Message": json.dumps({
        "notificationType": "Bounce",
        "bounce": {"bounceType": "Permanent", "bouncedRecipients": [{"emailAddress": "ses@x.in"}]},
    })}
    pm = {"RecordType": "SpamComplaint", "Email": "pm@x.in"}
    for body in (ses, pm):
        assert c.post("/api/v1/email/events/", body, format="json", HTTP_AUTHORIZATION=auth).status_code == 200
    assert is_suppressed("ses@x.in") and is_suppressed("pm@x.in")
    sub = {"Type": "SubscriptionConfirmation", "SubscribeURL": "https://evil.example.com/x"}
    assert c.post("/api/v1/email/events/", sub, format="json", HTTP_AUTHORIZATION=auth).status_code == 400


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", BOT_CHECK_PROVIDER="none")
def test_sign_up_code_to_a_suppressed_address_says_so(client):
    from core.mail import record_event

    record_event("gone@x.in", "hard_bounce")
    resp = client.post("/api/v1/auth/register/otp/request/", {"email": "gone@x.in"}, content_type="application/json")
    assert resp.status_code == 400 and "bounced" in resp.content.decode()


# --- WP-SC2 ---------------------------------------------------------------------------------


def test_break_glass_session_is_required_for_shell_in_production(monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    from core import breakglass

    monkeypatch.setenv("DJANGO_ENV", "production")
    monkeypatch.delenv("BREAKGLASS_SESSION_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        breakglass.enforce(["manage.py", "shell"])
    assert exc.value.code == 2
    breakglass.enforce(["manage.py", "migrate"])  # not interactive: allowed
    out = StringIO()
    call_command("breakglass_session", "open", "--staff", "ops@bizboard.test", "--ticket", "INC-7",
                 "--reason", "Fix a stuck import for a pilot", stdout=out)
    session_id = out.getvalue().split("BREAKGLASS_SESSION_ID=")[1].split()[0]
    monkeypatch.setenv("BREAKGLASS_SESSION_ID", session_id)
    breakglass.enforce(["manage.py", "shell"])
    from core.models import BreakGlassSession

    assert BreakGlassSession.objects.get(public_id=session_id).commands == ["shell"]
    BreakGlassSession.objects.filter(public_id=session_id).update(started_at=timezone.now() - timedelta(hours=3))
    with pytest.raises(SystemExit):
        breakglass.enforce(["manage.py", "shell"])
    monkeypatch.setenv("DJANGO_ENV", "development")
    monkeypatch.delenv("BREAKGLASS_SESSION_ID")
    breakglass.enforce(["manage.py", "shell"])  # dev: no session needed


# --- WP-CP2 ---------------------------------------------------------------------------------


def test_self_serve_export_lands_on_the_privacy_register(tenant_a):
    from support.models import DataPrivacyRequest

    with mock.patch("accounts.export_views.encrypt_export_zip", return_value=b"x"), \
         mock.patch("accounts.export_views.build_export_payload", return_value={"version": 1}), \
         mock.patch("accounts.export_views.summarise_export", return_value={}):
        resp = tenant_a.client.post("/api/v1/company/export/")
    assert resp.status_code == 200
    row = DataPrivacyRequest.objects.get(kind="ACCESS")
    assert row.closed_at is not None and row.company_id_hint == tenant_a.company.pk


# --- WP-PO2 ---------------------------------------------------------------------------------


def test_health_score_rewards_use_and_penalises_trouble(tenant_a):
    from billing.models import TenantActivation
    from support.health import band, score_company, snapshot_company
    from support.platform_tickets import open_ticket

    tenant_a.owner.last_login = timezone.now()
    tenant_a.owner.save(update_fields=["last_login"])
    TenantActivation.objects.update_or_create(
        company=tenant_a.company, defaults={"setup_completed_at": timezone.now(), "first_invoice_at": timezone.now()},
    )
    healthy, inputs = score_company(tenant_a.company)
    assert inputs["setup"] and inputs["first_invoice"] and inputs["days_since_login"] == 0
    open_ticket(company=tenant_a.company, user=tenant_a.owner, subject="Stock wrong", description="", severity="P1")
    worse, _ = score_company(tenant_a.company)
    assert worse == healthy - 10
    row = snapshot_company(tenant_a.company.pk)
    assert row.band == band(row.score)


def test_monthly_metrics_and_command(tenant_a):
    from io import StringIO

    from django.core.management import call_command

    from billing.platform_gst import issue_platform_gst_invoice
    from support.health import monthly_metrics

    issue_platform_gst_invoice(tenant_a.company, provider="razorpay", capture_id="pay_m", amount="1180")
    month = timezone.localdate().strftime("%Y-%m")
    data = monthly_metrics(month)
    assert data["paying_tenants"] == 1 and data["trial_to_paid"] == 1
    out = StringIO()
    call_command("saas_metrics", "--month", month, stdout=out)
    assert "paying_tenants" in out.getvalue()


def test_weekly_health_task_fans_out_per_company(tenant_a, tenant_b):
    from support import tasks

    with mock.patch.object(tasks.tenant_health_company_task, "delay") as delay:
        result = tasks.tenant_health_weekly_task()
    assert result["queued"] >= 2
    assert {c.kwargs["company_id"] for c in delay.call_args_list} >= {tenant_a.company.pk, tenant_b.company.pk}


def test_customer_record_says_when_its_email_is_suppressed(tenant_a):
    from core.mail import record_event
    from masters.models import Customer

    cust = Customer.objects.create(company=tenant_a.company, name="Bounce Traders", email="Gone@Bounce.in")
    resp = tenant_a.client.get(f"/api/v1/customers/{cust.pk}/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["data"]["emailSuppressed"] is False
    record_event("gone@bounce.in", "hard_bounce")
    assert tenant_a.client.get(f"/api/v1/customers/{cust.pk}/").json()["data"]["emailSuppressed"] is True


def test_admin_sms_guard_page_shows_status_and_only_superusers_flip_it(client):
    from core.services import sms_guard

    staff = User.objects.create_user(email="staff-sms@example.com", password="x-Strong-pass-1", is_staff=True)
    root = User.objects.create_superuser(email="root-sms@example.com", password="x-Strong-pass-1")
    client.force_login(staff)
    page = client.get("/admin/ops/sms-guard/")
    assert page.status_code == 200 and b"SMS today" in page.content
    assert client.post("/admin/ops/sms-guard/", {"kill": "on"}).status_code == 403
    assert sms_guard.kill_switch_on() is False
    client.force_login(root)
    assert client.post("/admin/ops/sms-guard/", {"kill": "on"}).status_code == 302
    assert sms_guard.kill_switch_on() is True
    client.post("/admin/ops/sms-guard/", {"kill": "off"})
    assert sms_guard.kill_switch_on() is False


def test_admin_saas_metrics_page_renders_month_and_weekly_table(client, tenant_a):
    root = User.objects.create_superuser(email="root-metrics@example.com", password="x-Strong-pass-1")
    client.force_login(root)
    month = timezone.localdate().strftime("%Y-%m")
    page = client.get(f"/admin/ops/saas-metrics/?month={month}")
    assert page.status_code == 200
    assert b"Time to first invoice by sign-up week" in page.content
    assert client.get("/admin/ops/saas-metrics/?month=bad").status_code == 302
