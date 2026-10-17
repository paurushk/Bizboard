"""GST-rate wording on the bill-import preview (no DB needed)."""

from imports.services import _preview_bill_line


def _warnings(rate):
    warnings: list[str] = []
    line = _preview_bill_line(
        {"name": "x", "quantity": "1", "unit_price": "10", "gst_rate": rate}, index=4, rate_warnings=warnings
    )
    return line, warnings


def test_out_of_slab_rate_is_not_reported_as_not_a_number():
    line, warnings = _warnings("9")
    assert line["include"] is False and line["gst_rate"] == ""
    assert "not a valid GST rate" in warnings[0]
    assert "not a number" not in warnings[0]


def test_text_rate_is_reported_as_not_a_number():
    _, warnings = _warnings("abc")
    assert "not a number" in warnings[0]


def test_valid_rate_has_no_warning():
    line, warnings = _warnings("18%")
    assert line["gst_rate"] == "18" and line["include"] is True and not warnings
