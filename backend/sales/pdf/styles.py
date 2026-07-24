"""ReportLab styles for the GST Tax Invoice template."""

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm

GREY_HEADER = colors.Color(0.92, 0.92, 0.92)
GREY_TOTAL = colors.Color(0.88, 0.88, 0.88)
LINE = colors.Color(0.55, 0.55, 0.55)
BLACK = colors.black


def build_styles():
    base = getSampleStyleSheet()
    return {
        "company_name": ParagraphStyle(
            "CompanyName",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=BLACK,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=BLACK,
        ),
        "title": ParagraphStyle(
            "InvoiceTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            alignment=TA_RIGHT,
        ),
        "copy_stamp": ParagraphStyle(
            "CopyStamp",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            alignment=TA_CENTER,
            leading=12,
        ),
        "section_head": ParagraphStyle(
            "SectionHead",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=BLACK,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
        ),
        "body_small": ParagraphStyle(
            "BodySmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=colors.Color(0.25, 0.25, 0.25),
        ),
        "th": ParagraphStyle(
            "TableHead",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            alignment=TA_CENTER,
        ),
        "td": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            alignment=TA_LEFT,
        ),
        "td_right": ParagraphStyle(
            "TableCellRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            alignment=TA_RIGHT,
        ),
        "td_center": ParagraphStyle(
            "TableCellCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            alignment=TA_CENTER,
        ),
        "total_label": ParagraphStyle(
            "TotalLabel",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            alignment=TA_RIGHT,
        ),
        "total_value": ParagraphStyle(
            "TotalValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            alignment=TA_RIGHT,
        ),
        "grand": ParagraphStyle(
            "Grand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            alignment=TA_RIGHT,
        ),
        "words": ParagraphStyle(
            "Words",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=10,
        ),
        "terms": ParagraphStyle(
            "Terms",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
        ),
    }


# Column widths for item table (sum ≈ 170mm usable width on A4 with 20mm margins)
COL_WIDTHS_TAX = [
    10 * mm,   # S.No
    52 * mm,   # Items
    18 * mm,   # HSN
    18 * mm,   # Qty
    16 * mm,   # MRP
    16 * mm,   # Rate
    20 * mm,   # Tax
    20 * mm,   # Amount
]

COL_WIDTHS_SIMPLE = [
    10 * mm,
    70 * mm,
    20 * mm,
    22 * mm,
    24 * mm,
    24 * mm,
]
