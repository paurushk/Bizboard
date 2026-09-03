"""CSV export helpers — formula-injection neutralization shared across writers."""


from decimal import Decimal


def csv_safe(value):
    """Neutralize CSV/Excel formula injection on export.

    A leading ``=``, ``+``, ``@``, tab, CR or LF is prefixed with a single quote
    so spreadsheet apps treat the cell as text. Numeric types and numeric-looking
    negatives are left untouched so Excel still parses amounts.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal)):
        return value
    text = str(value)
    if not text:
        return text
    stripped = text.lstrip(" \u00a0\t\r\n")
    if stripped and stripped[0] == "-":
        rest = stripped[1:].replace(".", "", 1)
        if rest.isdigit():
            return text
        return f"'{text}"
    # B7-008: include LF -- some CSV dialects re-split on a leading newline and
    # re-expose a formula. Also guard when the raw value starts with any of these
    # control chars before the visible payload.
    if (stripped and stripped[0] in ("=", "+", "@")) or (
        text[0] in ("\t", "\r", "\n", "=", "+", "@")
    ):
        return f"'{text}"
    return text
