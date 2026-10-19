"""SET-23: licence expiry, failed backup, quiet gateway and plan-limit alerts: sent once, to owners, in the app."""

from datetime import timedelta
from unittest import mock

from django.utils import timezone

from accounts.models import CompanyStatutoryLicence
from accounts.scheduled_backup import run_scheduled_backup
from accounts.settings_alerts import notify_owners, run_settings_alerts
from core.models import Notification

HEALTH = "/api/v1/company/settings-health/"


def _alerts(tenant):
    return Notification.objects.filter(company=tenant.company, channel=Notification.Channel.IN_APP)


def _licence(tenant, days_left, number="L-1"):
    return CompanyStatutoryLicence.objects.create(
        company=tenant.company, licence_type="FSSAI", licence_number=number,
        valid_upto=timezone.localdate() + timedelta(days=days_left), is_active=True,
    )


def test_a_licence_alert_is_sent_once_per_threshold(tenant_a):
    _licence(tenant_a, 20)
    assert run_settings_alerts(tenant_a.company) >= 1
    first = _alerts(tenant_a).count()
    assert first >= 1 and "expires in 30 days" in _alerts(tenant_a).first().subject
    run_settings_alerts(tenant_a.company)
    assert _alerts(tenant_a).count() == first


def test_closer_thresholds_alert_again_and_expiry_says_expired(tenant_a):
    lic = _licence(tenant_a, 20)
    run_settings_alerts(tenant_a.company)
    CompanyStatutoryLicence.objects.filter(pk=lic.pk).update(valid_upto=timezone.localdate() + timedelta(days=5))
    run_settings_alerts(tenant_a.company)
    CompanyStatutoryLicence.objects.filter(pk=lic.pk).update(valid_upto=timezone.localdate() - timedelta(days=1))
    run_settings_alerts(tenant_a.company)
    subjects = set(_alerts(tenant_a).values_list("subject", flat=True))
    assert {"Licence expires in 30 days", "Licence expires in 7 days", "Licence expired"} <= subjects


def test_far_off_or_inactive_licences_raise_nothing(tenant_a):
    _licence(tenant_a, 200, "FAR")
    lic = _licence(tenant_a, 3, "OFF")
    CompanyStatutoryLicence.objects.filter(pk=lic.pk).update(is_active=False)
    run_settings_alerts(tenant_a.company)
    assert not _alerts(tenant_a).filter(body__contains="Licence").exists()


def test_alerts_go_to_owners_only_and_stay_inside_the_company(tenant_a, tenant_b):
    notify_owners(tenant_a.company, "Hello", "Body", "test:1")
    recipients = set(_alerts(tenant_a).values_list("recipient", flat=True))
    assert tenant_a.owner.email in recipients and tenant_a.staff.email not in recipients
    assert _alerts(tenant_b).count() == 0


def test_a_failed_backup_alerts_the_owner_and_shows_in_the_checklist(tenant_a):
    tenant_a.company.scheduled_backup_enabled = True
    tenant_a.company.save(update_fields=["scheduled_backup_enabled"])
    with mock.patch("accounts.scheduled_backup.build_export_payload", side_effect=RuntimeError("disk full")):
        assert run_scheduled_backup(tenant_a.company) is None
    assert _alerts(tenant_a).filter(subject="Automatic backup failed").count() >= 1
    items = {i["id"]: i for i in tenant_a.client.get(HEALTH).data["items"]}
    assert items["backup"]["status"] == "warn"


def test_a_quiet_gateway_is_flagged_after_links_but_no_notifications(tenant_a):
    from payments.gateway import decrypt_gateway_credentials, encrypt_gateway_credentials, record_keys_accepted
    from payments.models import PaymentLink

    creds = {"key_id": "rzp_test_x", "key_secret": "y"}
    tenant_a.company.payment_gateway_provider = "razorpay"
    tenant_a.company.payment_gateway_credentials_encrypted = encrypt_gateway_credentials(creds)
    tenant_a.company.save(update_fields=["payment_gateway_provider", "payment_gateway_credentials_encrypted"])
    creds = decrypt_gateway_credentials(tenant_a.company.payment_gateway_credentials_encrypted)
    record_keys_accepted(tenant_a.company, creds, "razorpay")
    tenant_a.company.save(update_fields=["payment_gateway_credentials_encrypted"])
    assert "webhook" not in {i["id"] for i in tenant_a.client.get(HEALTH).data["items"]}
    PaymentLink.objects.create(company=tenant_a.company, token="tok-1", amount=100)
    items = {i["id"]: i for i in tenant_a.client.get(HEALTH).data["items"]}
    assert items["webhook"]["status"] == "warn"
    run_settings_alerts(tenant_a.company)
    assert _alerts(tenant_a).filter(subject="Payment notifications have gone quiet").exists()


def test_a_plan_limit_close_to_reached_is_flagged(tenant_a):
    from billing.quotas import usage_snapshot

    snap = usage_snapshot(tenant_a.company)
    fake = {k: dict(v) if isinstance(v, dict) else v for k, v in snap.items()}
    fake["seats"] = {"limit": 5, "used": 5}
    with mock.patch("billing.quotas.usage_snapshot", return_value=fake):
        run_settings_alerts(tenant_a.company)
        items = {i["id"]: i for i in tenant_a.client.get(HEALTH).data["items"]}
    assert items["plan"]["status"] == "warn" and "seats" in items["plan"]["metrics"]
    assert _alerts(tenant_a).filter(subject="Plan limit reached").exists()
