"""OTP hash helpers and integrity-error envelope hardening."""

from django.db import IntegrityError
from django.test import override_settings
from unittest.mock import MagicMock, patch

import pytest

from accounts.otp_utils import hash_otp, verify_otp
from core.exceptions import BusinessRuleError, api_exception_handler


@override_settings(OTP_PEPPER="unit-test-pepper")
def test_hash_otp_and_verify_roundtrip():
    digest = hash_otp("123456")
    assert len(digest) == 64
    assert digest != "123456"
    assert verify_otp(digest, "123456")
    assert not verify_otp(digest, "000000")
    assert not verify_otp("", "123456")


@override_settings(OTP_PEPPER="unit-test-pepper")
def test_hash_otp_is_deterministic_and_pepper_sensitive():
    a = hash_otp("999999")
    b = hash_otp("999999")
    assert a == b
    with override_settings(OTP_PEPPER="other-pepper"):
        assert hash_otp("999999") != a


def test_integrity_error_hides_raw_details():
    resp = api_exception_handler(
        IntegrityError("UNIQUE constraint failed: secret_table.secret_col"),
        context=None,
    )
    assert resp is not None
    assert resp.status_code == 400
    assert resp.data["success"] is False
    assert resp.data["error"]["code"] == "integrity_error"
    assert resp.data["error"]["details"] is None
    assert "secret_table" not in str(resp.data)
    assert "UNIQUE" not in str(resp.data)


@override_settings(MSG91_AUTH_KEY="test-key", MSG91_TEMPLATE_ID="tpl")
@patch("core.services.sms.urllib.request.urlopen")
def test_msg91_non_json_body_is_failure(mock_urlopen):
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = b"OK"
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    mock_urlopen.return_value = resp
    from core.services.sms import _send_msg91

    with pytest.raises(BusinessRuleError, match="invalid"):
        _send_msg91("+919876543210", "123456")


@override_settings(MSG91_AUTH_KEY="test-key", MSG91_TEMPLATE_ID="tpl")
@patch("core.services.sms.urllib.request.urlopen")
def test_msg91_empty_body_is_failure(mock_urlopen):
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = b""
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    mock_urlopen.return_value = resp
    from core.services.sms import _send_msg91

    with pytest.raises(BusinessRuleError, match="empty"):
        _send_msg91("+919876543210", "123456")


def test_canonicalize_user_phone_collapses_indian_formats():
    from accounts.otp_utils import canonicalize_user_phone, phone_lookup_values

    assert canonicalize_user_phone("9876543210") == "+919876543210"
    assert canonicalize_user_phone("+919876543210") == "+919876543210"
    assert canonicalize_user_phone("919876543210") == "+919876543210"
    variants = phone_lookup_values("9876543210")
    assert "+919876543210" in variants
    assert "9876543210" in variants
