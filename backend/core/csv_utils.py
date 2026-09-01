"""CSV export helpers — formula-injection neutralization shared across writers."""


from decimal import Decimal


def csv_safe(value):
    """Neutralize CSV/Excel formula injection on export.

    A leading ``=``, ``+``, or ``@`` is prefixed with a single quote so
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
    if text[0] == "-":
        rest = text[1:].replace(".", "", 1)
        if rest.isdigit():
            return text
        return f"'{text}"
    if text[0] in ("=", "+", "@"):
        return f"'{text}"
    return text
