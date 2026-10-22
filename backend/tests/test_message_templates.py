"""WP-CM2: every SMS is a registered DLT template; raw bodies are refused."""

import json
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings

from core.exceptions import BusinessRuleError
from core.message_templates import MAX_SMS_LENGTH, SMS_TEMPLATES, sms_template
from core.services.sms import SmsProvider

PHONE = "+919820012345"
SAMPLE = {
    "otp": {"code": "123456"},
    "payment_reminder": {
        "company": "A Very Long Company Name Private Limited Traders And Distributors",
        "number": "INV/2026-27/000123",
        "amount": "1234567.89",
        "due_date": "2026-10-01",
    },
}


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.parametrize("key", sorted(SMS_TEMPLATES))
def test_every_template_renders_within_length(key):
    assert key in SAMPLE, f"add sample values for '{key}'"
    text = sms_template(key).render(**SAMPLE[key])
    assert 0 < len(text) <= MAX_SMS_LENGTH
    assert "{" not in text


def test_missing_variable_and_unknown_key_are_refused():
    with pytest.raises(BusinessRuleError, match="missing"):
        sms_template("payment_reminder").render(company="X")
    with pytest.raises(BusinessRuleError, match="not a registered"):
        SmsProvider.send_template(PHONE, "free_text", body="hi")


@override_settings(DJANGO_ENV="production", DEBUG=False, SMS_PROVIDER="msg91", MSG91_AUTH_KEY="k",
                   SMS_DLT_TEMPLATE_PAYMENT_REMINDER="")
def test_production_refuses_a_template_with_no_dlt_id_for_indian_numbers():
    with mock.patch("core.services.sms.urllib.request.urlopen") as urlopen:
        with pytest.raises(BusinessRuleError, match="no DLT template ID"):
            SmsProvider.send_template(PHONE, "payment_reminder", **SAMPLE["payment_reminder"])
    urlopen.assert_not_called()


@override_settings(DJANGO_ENV="production", DEBUG=False, SMS_PROVIDER="msg91", MSG91_AUTH_KEY="k",
                   SMS_DLT_TEMPLATE_PAYMENT_REMINDER="dlt-123")
def test_msg91_sends_non_otp_sms_by_dlt_template_id():
    resp = mock.MagicMock(status=200)
    resp.read.return_value = b'{"type": "success"}'
    resp.__enter__.return_value = resp
    with mock.patch("core.services.sms.urllib.request.urlopen", return_value=resp) as urlopen:
        SmsProvider.send_template("9820012345", "payment_reminder", **SAMPLE["payment_reminder"])
    req = urlopen.call_args[0][0]
    payload = json.loads(req.data)
    assert payload["template_id"] == "dlt-123"
    assert payload["recipients"][0]["mobiles"] == "919820012345"
    assert payload["recipients"][0]["number"] == "INV/2026-27/000123"


def test_notification_sms_without_a_template_is_marked_failed(tenant_a):
    from core.models import Notification
    from core.services.notifications import NotificationService

    company = tenant_a.company
    n = NotificationService.send(
        company=company, channel=Notification.Channel.SMS, recipient=PHONE, subject="ad_hoc", body="Pay now",
    )
    assert n.status == Notification.Status.FAILED
    assert "registered template" in n.error

    ok = NotificationService.send(
        company=company, channel=Notification.Channel.SMS, recipient=PHONE, subject="payment_reminder",
        body="x", template_vars=SAMPLE["payment_reminder"],
    )
    assert ok.status == Notification.Status.SENT


def test_guard_passes_on_the_repo():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "ci_gates" / "guards" / "guard_message_templates.py"
    spec = importlib.util.spec_from_file_location("guard_message_templates", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.check(root) == []
