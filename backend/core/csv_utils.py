"""CSV export helpers — formula-injection neutralization shared across writers."""


from decimal import Decimal


def csv_safe(value):
    """Neutralize CSV/Excel formula injection on export.

    A leading ``=``, ``+``, ``@``, tab, or CR is prefixed with a single quote so
    spreadsheet apps treat the cell as text. Numeric types and numeric-looking
    negatives are left untouched so Excel still parses amounts.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal)):
        return value
    text = str(value)
    if not text:
        return text
    stripped = text.lstrip(" \u00a0")
    if stripped and stripped[0] == "-":
        rest = stripped[1:].replace(".", "", 1)
        if rest.isdigit():
            return text
        return f"'{text}"
    if stripped and stripped[0] in ("=", "+", "@", "\t", "\r"):
        return f"'{text}"
    return text
