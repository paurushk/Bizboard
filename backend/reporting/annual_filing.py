"""Annual return (GSTR-9) filing date, used for the Sec 34(2) note time limit."""

from datetime import date

from .models import AnnualReturnFiling


def fy_start_year_of(d: date) -> int:
    return d.year if d.month >= 4 else d.year - 1


def note_deadline(company, invoice_date: date) -> date:
    """Earlier of 30 Nov after the invoice's FY and the date its annual return was filed."""
    fy_start = fy_start_year_of(invoice_date)
    deadline = date(fy_start + 1, 11, 30)
    filed = (
        AnnualReturnFiling.objects.filter(company=company, fy_start_year=fy_start)
        .values_list("filed_on", flat=True)
        .first()
    )
    return min(deadline, filed) if filed else deadline
