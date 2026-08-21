"""GSTN Unit Quantity Code (UQC) helpers for GSTR Table 12 / e-docs."""

from __future__ import annotations

# Common GSTN UQC codes (subset sufficient for SMB retail/wholesale).
GSTN_UQC_CODES = (
    "BAG",
    "BAL",
    "BDL",
    "BKL",
    "BOU",
    "BOX",
    "BTL",
    "BUN",
    "CAN",
    "CBM",
    "CCM",
    "CMS",
    "CTN",
    "DOZ",
    "DRM",
    "GGK",
    "GMS",
    "GRS",
    "GYD",
    "KGS",
    "KLR",
    "KME",
    "LTR",
    "MLT",
    "MTR",
    "MTS",
    "NOS",
    "OTH",
    "PAC",
    "PCS",
    "PRS",
    "QTL",
    "ROL",
    "SET",
    "SQF",
    "SQM",
    "SQY",
    "TBS",
    "TGM",
    "THD",
    "TON",
    "TUB",
    "UGS",
    "UNT",
    "YDS",
)

# Free-text unit aliases → GSTN UQC
_UNIT_ALIASES = {
    "PCS": "PCS",
    "PC": "PCS",
    "PIECE": "PCS",
    "PIECES": "PCS",
    "NOS": "NOS",
    "NO": "NOS",
    "NUMBER": "NOS",
    "NUMBERS": "NOS",
    "EACH": "NOS",
    "EA": "NOS",
    "KG": "KGS",
    "KGS": "KGS",
    "KILOGRAM": "KGS",
    "KILOGRAMS": "KGS",
    "G": "GMS",
    "GM": "GMS",
    "GMS": "GMS",
    "GRAM": "GMS",
    "GRAMS": "GMS",
    "LTR": "LTR",
    "L": "LTR",
    "LITRE": "LTR",
    "LITER": "LTR",
    "LITRES": "LTR",
    "ML": "MLT",
    "MLT": "MLT",
    "MILLILITRE": "MLT",
    "MILLILITER": "MLT",
    "MILLILITRES": "MLT",
    "MTR": "MTR",
    "M": "MTR",
    "METER": "MTR",
    "METRE": "MTR",
    "METERS": "MTR",
    "BOX": "BOX",
    "BX": "BOX",
    "CTN": "CTN",
    "CARTON": "CTN",
    "BAG": "BAG",
    "SET": "SET",
    "DOZ": "DOZ",
    "DOZEN": "DOZ",
    "TON": "TON",
    "MT": "MTS",
    "MTS": "MTS",
    "SQM": "SQM",
    "SQF": "SQF",
    "PAC": "PAC",
    "PACK": "PAC",
    "PKT": "PAC",
    "BTL": "BTL",
    "BOTTLE": "BTL",
    "ROL": "ROL",
    "ROLL": "ROL",
    "UNT": "UNT",
    "UNIT": "UNT",
    "OTH": "OTH",
    "OTHER": "OTH",
}


def normalize_uqc(value: str | None) -> str:
    """Return a GSTN UQC code or empty string if unmapped."""
    if not value:
        return ""
    key = value.strip().upper()
    if key in GSTN_UQC_CODES:
        return key
    return _UNIT_ALIASES.get(key, "")


def resolve_uqc_code(
    *,
    explicit: str | None = None,
    unit=None,
    unit_name: str | None = None,
) -> str:
    """Prefer explicit → Unit.uqc_code → heuristic from unit short/name → unit_name text."""
    code = normalize_uqc(explicit)
    if code:
        return code
    if unit is not None:
        code = normalize_uqc(getattr(unit, "uqc_code", "") or "")
        if code:
            return code
        code = normalize_uqc(getattr(unit, "short_name", "") or "")
        if code:
            return code
        code = normalize_uqc(getattr(unit, "name", "") or "")
        if code:
            return code
    return normalize_uqc(unit_name) or ""


def snapshot_unit_fields(product, line: dict | None = None) -> dict:
    """Build hsn_code / unit_name / uqc_code snapshots for a document line."""
    line = line or {}
    unit = getattr(product, "unit", None)
    unit_name = (
        line.get("unit_name")
        or (unit.short_name.upper() if unit and unit.short_name else None)
        or (unit.name.upper()[:16] if unit and unit.name else None)
        or "PCS"
    )
    uqc = resolve_uqc_code(
        explicit=line.get("uqc_code"),
        unit=unit,
        unit_name=unit_name,
    )
    if not uqc:
        uqc = normalize_uqc(unit_name) or "OTH"
    return {
        "hsn_code": (line.get("hsn_code") or getattr(product, "hsn_code", None) or "") or "",
        "unit_name": unit_name,
        "uqc_code": uqc,
    }
