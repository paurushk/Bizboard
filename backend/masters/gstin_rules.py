"""GSTIN side-effects for party masters (CUS-21).

Pure helpers (no DB writes). ``CustomerSerializer.validate`` calls them, and because the view
applies ``serializer.validated_data`` with ``setattr``, whatever ``validate`` adds to ``attrs``
is persisted by every write path (view PATCH/PUT, plain ``serializer.save()``, import).
"""

from __future__ import annotations

from core.services.tax_engine.india import IN_STATE_NAME_TO_CODE
from core.validators import GSTIN_RE

# Codes with no single Indian state to compare against (export / other territory).
NO_SINGLE_STATE = frozenset({"96", "97"})

# Canonical display name for each GST state code. Names resolve back through IN_STATE_NAME_TO_CODE.
GST_CODE_TO_STATE = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman and Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh",
}

# What a changed or cleared GSTIN does to the stored verification (it described the old number).
VERIFICATION_RESET = {
    "gstin_verification_status": "UNVERIFIED",
    "gstin_legal_name": "",
    "gstin_verified_at": None,
    "gstin_raw_payload": None,
}


def normalise(gstin) -> str:
    return (gstin or "").strip().upper()


def state_code_of_gstin(gstin: str) -> str | None:
    """The 2-digit state code of a well-formed GSTIN, or None."""
    gstin = normalise(gstin)
    return gstin[:2] if GSTIN_RE.match(gstin) else None


def derive_state(gstin: str) -> str | None:
    """Canonical state name for a GSTIN prefix; None when there is no single state."""
    code = state_code_of_gstin(gstin)
    if code is None or code in NO_SINGLE_STATE:
        return None
    return GST_CODE_TO_STATE.get(code)


def derive_pan(gstin: str) -> str:
    gstin = normalise(gstin)
    return gstin[2:12] if GSTIN_RE.match(gstin) else ""


def state_code_of_name(state: str) -> str | None:
    return IN_STATE_NAME_TO_CODE.get((state or "").strip().lower())


def state_conflicts(gstin: str, state: str) -> str | None:
    """Expected canonical state when ``state`` clearly disagrees with the GSTIN prefix, else None.

    Unknown or free-text state names never conflict: only a recognised state with a different code does.
    """
    code = state_code_of_gstin(gstin)
    if code is None or code in NO_SINGLE_STATE or not (state or "").strip():
        return None
    named = state_code_of_name(state)
    if named is None or named == code:
        return None
    return GST_CODE_TO_STATE.get(code)
