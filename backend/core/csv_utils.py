"""CSV export helpers — formula-injection neutralization shared across writers."""


def csv_safe(value):
    """Neutralize CSV/Excel formula injection on export.

    A leading ``=``, ``+``, ``-``, or ``@`` is prefixed with a single quote so
    spreadsheet apps treat the cell as text. Numeric types are left untouched.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@"):
        return f"'{text}"
    return text
