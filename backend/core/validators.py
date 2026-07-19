"""GSTIN / HSN / GST-rate validation helpers (E1.10)."""

import re

from django.core.exceptions import ValidationError

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
HSN_RE = re.compile(r"^\d{4}(\d{2})?(\d{2})?$")  # 4, 6 or 8 digits

ALLOWED_GST_RATES = ("0", "0.25", "3", "5", "12", "18", "28")


def validate_gstin(value):
    if value and not GSTIN_RE.match(value):
        raise ValidationError("Invalid GSTIN format.")


def validate_hsn(value):
    if value and not HSN_RE.match(value):
        raise ValidationError("Invalid HSN/SAC code — must be 4, 6 or 8 digits.")


def validate_gst_rate(value):
    from decimal import Decimal

    if Decimal(value) not in tuple(Decimal(r) for r in ALLOWED_GST_RATES):
        raise ValidationError(
            f"Invalid GST rate {value}. Allowed: {', '.join(ALLOWED_GST_RATES)}%."
        )
