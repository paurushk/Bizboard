"""OTP hash helpers and integrity-error envelope hardening."""

from django.db import IntegrityError
from django.test import override_settings

from accounts.otp_utils import hash_otp, verify_otp
from core.exceptions import api_exception_handler


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
