"""WP-F4 / DIM6-07: documents and the general ledger must tell the same story.

The GL invariants in ``gl.py`` prove the ledger is internally consistent (balanced, TB = 0).
These prove it agrees with the documents it was posted from:

- AR / AP: the 1200 / 2100 control accounts equal their party-tagged lines, and those equal
  document outstanding (open invoices, notes and party opening balances, net of allocations).
  The comparison is ``BooksHealthService.control_balances`` — the same one the Books health
  screen and the period-close gate use, so there is one definition of "ties".
- Output GST: for every posted sales invoice, the GST credited to the output tax accounts
  equals the tax on the invoice lines (the posting rule since R3-015).

Stock value vs the inventory account is deliberately not an invariant: valuation is periodic
and perpetual FIFO COGS is out of scope (QOS-0072), so the two are not meant to be equal.

Each check returns [] for a company that does not post to the ledger (``posts_to_ledger``).
"""

from __future__ import annotations

from accounting.books import posts_to_ledger
from decimal import Decimal

from .base import invariant

_TOLERANCE = Decimal("0.05")
OUTPUT_GST_CODES = ("2210", "2220", "2230", "2270")
_AR_CODES = {"AR_CONTROL_MISMATCH", "DOCS_GL_AR_MISMATCH"}
_AP_CODES = {"AP_CONTROL_MISMATCH", "DOCS_GL_AP_MISMATCH"}


def _control_alerts(company) -> list[dict]:
    from accounting.services import BooksHealthService

    return BooksHealthService.control_balances(company).get("alerts", [])


@invariant(
    "gl.ar_ties_to_documents",
    consequence="Receivables in the ledger (1200 and the customer ledgers) differ from what the invoices say is owed.",
)
def ar_ties_to_documents(company) -> list[str]:
    if not posts_to_ledger(company):
        return []
    return [f"{a['code']}: {a['message']}" for a in _control_alerts(company) if a.get("code") in _AR_CODES]


@invariant(
    "gl.ap_ties_to_documents",
    consequence="Payables in the ledger (2100 and the supplier ledgers) differ from what the bills say is owed.",
)
def ap_ties_to_documents(company) -> list[str]:
    if not posts_to_ledger(company):
        return []
    return [f"{a['code']}: {a['message']}" for a in _control_alerts(company) if a.get("code") in _AP_CODES]


@invariant(
    "gl.sales_output_gst_ties_to_invoices",
    consequence="GST posted to the output tax accounts for an invoice differs from the tax on its lines; GSTR-1 and the ledger disagree.",
)
def sales_output_gst_ties_to_invoices(company) -> list[str]:
    if not posts_to_ledger(company):
        return []
    from django.db.models import F, Sum

    from accounting.models import JournalEntry, JournalLine
    from sales.models import SalesInvoice

    posted = (
        JournalLine.objects.filter(
            entry__company=company,
            entry__source_type="SALES_INVOICE",
            entry__status=JournalEntry.Status.POSTED,
            account__code__in=OUTPUT_GST_CODES,
        )
        .values("entry__source_id")
        .annotate(c=Sum("credit"), d=Sum("debit"))
    )
    gl_tax = {r["entry__source_id"]: (r["c"] or Decimal("0")) - (r["d"] or Decimal("0")) for r in posted}
    if not gl_tax:
        return []
    invoices = (
        SalesInvoice.objects.filter(company=company, pk__in=list(gl_tax))
        .exclude(status=SalesInvoice.Status.CANCELLED)
        .annotate(line_tax=Sum(F("items__cgst") + F("items__sgst") + F("items__igst") + F("items__cess")))
        .values_list("pk", "number", "line_tax")
    )
    from accounting.services import taxable_charge_line

    out = []
    for pk, number, line_tax in invoices:
        expected = line_tax or Decimal("0")
        invoice = SalesInvoice.objects.filter(pk=pk).only(
            "additional_charges", "charges_gst_rate", "charges_hsn", "igst_total",
        ).first()
        charge = taxable_charge_line(invoice, Decimal("1") if invoice.igst_total else Decimal("0"))
        if charge is not None:  # taxable freight/packing carries its own GST (R3-015 posts it too)
            expected += charge.cgst + charge.sgst + charge.igst
        diff = gl_tax[pk] - expected
        if abs(diff) > _TOLERANCE:
            out.append(f"invoice {number or pk}: output GST posted {gl_tax[pk]} vs line tax {expected}")
    return out
