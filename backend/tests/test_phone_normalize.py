"""Sign-up / invite mobile numbers: forgive how people type them, store E.164."""

import pytest
from rest_framework import serializers

from accounts.otp_utils import PHONE_INVALID_MESSAGE, canonicalize_new_phone, normalize_e164
from accounts.serializers import InviteUserSerializer, RegisterSerializer


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+919876543210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        # Trunk 0, the way most Indians write a mobile.
        ("09876543210", "+919876543210"),
        ("+91 098765 43210", "+919876543210"),
        # Spaces, hyphens, brackets and dots.
        ("+91 98765 43210", "+919876543210"),
        ("98765-43210", "+919876543210"),
        ("(+91) 98765.43210", "+919876543210"),
        # 00 international prefix and a foreign number.
        ("0091 98765 43210", "+919876543210"),
        ("+971 50 123 4567", "+971501234567"),
        ("0044 7911 123456", "+447911123456"),
    ],
)
def test_normalize_accepts_common_formats(raw, expected):
    assert normalize_e164(raw) == expected


@pytest.mark.parametrize("raw", ["", "not-a-phone", "98765", "5123456789", "0123456789", "+0123456789"])
def test_normalize_rejects_with_plain_message(raw):
    with pytest.raises(ValueError) as exc:
        normalize_e164(raw)
    assert str(exc.value) == PHONE_INVALID_MESSAGE
    assert "E.164" not in str(exc.value)


def test_register_serializer_phone_error_is_on_the_field():
    s = RegisterSerializer()
    assert s.validate_phone("098765 43210") == "+919876543210"
    assert s.validate_phone("") == ""
    with pytest.raises(serializers.ValidationError) as exc:
        s.validate_phone("12345")
    assert PHONE_INVALID_MESSAGE in str(exc.value.detail)


@pytest.mark.parametrize("raw", ["+91 98765 4321", "+91 98765 432100", "+91 12345 67890"])
def test_new_phone_rejects_incomplete_indian_number(raw):
    # normalize_e164 keeps these (stored numbers must still save), new entries may not.
    normalize_e164(raw)
    with pytest.raises(ValueError):
        canonicalize_new_phone(raw)
    with pytest.raises(serializers.ValidationError):
        RegisterSerializer().validate_phone(raw)


@pytest.mark.django_db
def test_invite_rejects_incomplete_indian_number():
    with pytest.raises(serializers.ValidationError):
        InviteUserSerializer().validate_phone("+91987654321")


def test_new_phone_keeps_valid_numbers():
    assert canonicalize_new_phone("+91 98765 43210") == "+919876543210"
    assert canonicalize_new_phone("+971 50 123 4567") == "+971501234567"
