"""GSTIN / HSN / GST-rate validation helpers (E1.10)."""

import re

from django.core.exceptions import ValidationError

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
HSN_RE = re.compile(r"^\d{4}(\d{2})?(\d{2})?$")  # 4, 6 or 8 digits
# PAY-13: UPI VPA — local-part @ PSP handle (e.g. shop@oksbi).
UPI_VPA_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")

ALLOWED_GST_RATES = ("0", "0.25", "3", "5", "12", "18", "28", "40")


def _gstin_checksum_ok(gstin: str) -> bool:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    gstin = gstin.upper()
    total = 0
    for i, ch in enumerate(gstin[:14]):
        code = chars.index(ch)
        factor = 1 + (i % 2)  # 1,2,1,2...
        product = code * factor
        total += (product // 36) + (product % 36)
    check = (36 - (total % 36)) % 36
    return chars[check] == gstin[14]


def validate_gstin(value):
    if not value:
        return
    gstin = value.upper()
    if not GSTIN_RE.match(gstin):
        raise ValidationError("Invalid GSTIN format.")
    if not _gstin_checksum_ok(gstin):
        raise ValidationError("Invalid GSTIN checksum.")


def validate_pan(value):
    if not value:
        return
    pan = str(value).strip().upper()
    if not PAN_RE.match(pan):
        raise ValidationError("Invalid PAN format — expected 5 letters, 4 digits, 1 letter.")


def validate_udyam(value):
    if not value:
        return
    udyam = str(value).strip().upper()
    if not UDYAM_RE.match(udyam):
        raise ValidationError("Invalid UDYAM number — expected UDYAM-XX-00-0000000.")


def validate_hsn(value):
    if value and not HSN_RE.match(value):
        raise ValidationError("Invalid HSN/SAC code — must be 4, 6 or 8 digits.")


def validate_gst_rate(value):
    from decimal import Decimal

    if Decimal(value) not in tuple(Decimal(r) for r in ALLOWED_GST_RATES):
        raise ValidationError(
            f"Invalid GST rate {value}. Allowed: {', '.join(ALLOWED_GST_RATES)}%."
        )


def validate_upi_vpa(value):
    """Validate company UPI ID as user@bank VPA (blank allowed)."""
    if not value:
        return
    vpa = str(value).strip()
    if not UPI_VPA_RE.match(vpa):
        raise ValidationError(
            "Invalid UPI ID — use the form user@bank (e.g. shopname@oksbi)."
        )
