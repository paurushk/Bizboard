"""GP7 / QOS-0046 — WhatsApp template delivery against a mocked Cloud API.

The invoice-with-payment-link template (GD-25) is the first approved template. Nothing here
calls Meta: the HTTP client is mocked and credentials are patched in, so no secret is needed.
Delivery honesty matters most: only a real message id counts as SENT, and every other outcome
must say what actually happened.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.models import Notification
from core.services import whatsapp
from core.services.notifications import NotificationService

pytestmark = pytest.mark.django_db

PHONE = "+91 98765 43210"
FLAGS_ON = {"ENABLE_WHATSAPP_CLOUD": True}


def _response(status_code=200, body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body if body is not None else {}
    resp.text = text
    return resp


def _cloud(post_response):
    """Patch the flag, the tenant credentials and the HTTP client for one test."""
    return (
        patch.object(whatsapp, "build_feature_flags", return_value=FLAGS_ON),
        patch.object(whatsapp, "_resolve_whatsapp_credentials", return_value=("tok", "12345")),
        patch.object(whatsapp.requests, "post", return_value=post_response),
    )


def test_payment_link_template_is_approved_and_reminder_is_still_there():
    assert "invoice_with_payment_link" in whatsapp.APPROVED_WHATSAPP_TEMPLATES
    assert "payment_reminder" in whatsapp.APPROVED_WHATSAPP_TEMPLATES


def test_cloud_send_posts_the_payment_link_template_with_its_body_params():
    flags, creds, post = _cloud(_response(200, {"messages": [{"id": "wamid.GD25"}]}))
    with flags, creds, post as mock_post:
        result = whatsapp.send_whatsapp_template(
            PHONE,
            "invoice_with_payment_link",
            ["INV-7", "1,180.00", "https://pay.example/abc"],
            company=object(),
            language_code="en",
            opt_in=True,
        )

    assert (result.mode, result.message_id) == ("cloud", "wamid.GD25")
    (url,), kwargs = mock_post.call_args
    assert url.endswith("/12345/messages")
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    template = kwargs["json"]["template"]
    assert template["name"] == "invoice_with_payment_link"
    assert [p["text"] for p in template["components"][0]["parameters"]] == [
        "INV-7",
        "1,180.00",
        "https://pay.example/abc",
    ]
    assert kwargs["json"]["to"] == "919876543210"  # digits only


def test_an_unapproved_template_never_reaches_the_cloud():
    flags, creds, post = _cloud(_response(200, {"messages": [{"id": "x"}]}))
    with flags, creds, post as mock_post:
        result = whatsapp.send_whatsapp_template(PHONE, "birthday_blast", ["hi"], company=object())

    assert result.mode == "link"
    assert result.share_link.startswith("https://wa.me/919876543210")
    mock_post.assert_not_called()


def test_cloud_disabled_sends_a_link_not_a_message():
    with patch.object(whatsapp, "build_feature_flags", return_value={}), patch.object(
        whatsapp.requests, "post"
    ) as mock_post:
        result = whatsapp.send_whatsapp_template(PHONE, "invoice_with_payment_link", ["x"], company=object())

    assert result.mode == "link"
    mock_post.assert_not_called()


def test_http_error_is_reported_as_failed_with_the_status():
    flags, creds, post = _cloud(_response(400, text="template not found"))
    with flags, creds, post:
        result = whatsapp.send_whatsapp_template(
            PHONE, "invoice_with_payment_link", ["x"], company=object(), opt_in=True,
        )

    assert result.mode == "failed"
    assert result.raw["status_code"] == 400


@pytest.mark.parametrize("body", [{}, {"messages": []}, {"messages": [{}]}])
def test_a_reply_without_a_message_id_is_never_treated_as_sent(body):
    flags, creds, post = _cloud(_response(200, body))
    with flags, creds, post:
        result = whatsapp.send_whatsapp_template(
            PHONE, "invoice_with_payment_link", ["x"], company=object(), opt_in=True,
        )

    assert result.mode == "link"
    assert result.message_id == ""
    assert "error" in result.raw


def test_notification_marks_sent_only_with_a_message_id(tenant_a):
    flags, creds, post = _cloud(_response(200, {"messages": [{"id": "wamid.OK"}]}))
    with flags, creds, post:
        sent = NotificationService.send(
            company=tenant_a.company,
            channel=Notification.Channel.WHATSAPP,
            recipient=PHONE,
            subject="invoice_with_payment_link",
            body="INV-7 https://pay.example/abc",
        )
    assert sent.status == Notification.Status.SENT
    assert sent.share_link == "wamid.OK"


def test_notification_records_a_cloud_failure_instead_of_claiming_delivery(tenant_a):
    flags, creds, post = _cloud(_response(500, text="upstream down"))
    with flags, creds, post:
        failed = NotificationService.send(
            company=tenant_a.company,
            channel=Notification.Channel.WHATSAPP,
            recipient=PHONE,
            subject="invoice_with_payment_link",
            body="INV-7",
        )
    assert failed.status == Notification.Status.FAILED
    assert "HTTP 500" in failed.error


def test_notification_without_cloud_is_a_ready_link_never_sent(tenant_a):
    with patch.object(whatsapp, "build_feature_flags", return_value={}):
        link = NotificationService.send(
            company=tenant_a.company,
            channel=Notification.Channel.WHATSAPP,
            recipient=PHONE,
            subject="invoice_with_payment_link",
            body="INV-7",
        )
    assert link.status == Notification.Status.LINK_READY
    assert link.share_link.startswith("https://wa.me/")


def test_an_unknown_subject_falls_back_to_a_known_template(tenant_a):
    with patch.object(whatsapp, "send_whatsapp_template", wraps=whatsapp.send_whatsapp_template) as spy, patch.object(
        whatsapp, "build_feature_flags", return_value={}
    ):
        NotificationService.send(
            company=tenant_a.company,
            channel=Notification.Channel.WHATSAPP,
            recipient=PHONE,
            subject="Your invoice is overdue",
            body="x",
        )
    assert spy.call_args.kwargs["template_name"] == "invoice_share"
