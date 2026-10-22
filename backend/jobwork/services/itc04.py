"""ITC-04: goods sent for job work, and what came back (MFG-25).

Table 4 lists challans (goods sent), tables 5A, 5B and 5C list what the job worker did with them,
each row tied to the challan it settles (number and date) through ``JobWorkSettlement``.
Frequency comes from manufacturing settings: yearly up to Rs 5 crore turnover, half-yearly above.
"""

import csv
import io
from datetime import date

from django.db import transaction

from core.csv_utils import csv_safe

from jobwork.models import (
    Itc04Filing, JobWorkChallan, JobWorkChallanLine, JobWorkReceiptLine, JobWorkSettlement,
)

from .common import d, money, rule

K = JobWorkReceiptLine.Kind


def fy_start_year(on: date) -> int:
    return on.year if on.month >= 4 else on.year - 1


def period(frequency: str, fy_year: int, half: int | None = None):
    """(label, from, to, due) for a financial year, or one half of it."""
    if frequency == "HALF_YEARLY":
        if half not in (1, 2):
            raise rule("Choose the first or second half of the year.", "JW_BAD_PERIOD")
        if half == 1:
            return (f"{fy_year}-{str(fy_year + 1)[-2:]} H1", date(fy_year, 4, 1), date(fy_year, 9, 30), date(fy_year, 10, 25))
        return (f"{fy_year}-{str(fy_year + 1)[-2:]} H2", date(fy_year, 10, 1), date(fy_year + 1, 3, 31), date(fy_year + 1, 4, 25))
    return (f"{fy_year}-{str(fy_year + 1)[-2:]}", date(fy_year, 4, 1), date(fy_year + 1, 3, 31), date(fy_year + 1, 4, 25))


def periods_due(frequency: str, on: date):
    """The period that has just ended (or is current), with its due date, for reminders."""
    fy = fy_start_year(on)
    if frequency == "HALF_YEARLY":
        return [period(frequency, fy, 1), period(frequency, fy, 2), period(frequency, fy - 1, 2)]
    return [period(frequency, fy), period(frequency, fy - 1)]


def _uqc(product):
    unit = getattr(product, "unit", None)
    return (getattr(unit, "uqc_code", "") or getattr(unit, "short_name", "") or "").upper()


def build(company, date_from: date, date_to: date) -> dict:
    """The ITC-04 tables for a period."""
    t4, t5a, t5b, t5c = [], [], [], []
    lines = JobWorkChallanLine.objects.filter(
        company=company, challan__order__direction="OUT", challan__status="ISSUED",
        challan__challan_date__gte=date_from, challan__challan_date__lte=date_to,
    ).select_related("challan__order__supplier", "product__unit")
    for ln in lines:
        ch, sup = ln.challan, ln.challan.order.supplier
        if ch.origin == JobWorkChallan.Origin.FROM_OTHER_JOB_WORKER:
            continue    # passing goods on is reported in table 5B, not as a fresh sending
        t4.append({
            "challan_no": ch.number, "challan_date": ch.challan_date, "job_worker": sup.name,
            "gstin": sup.gstin or "", "state": sup.state or "", "product": ln.product.name,
            "hsn": ln.product.hsn_code, "uqc": _uqc(ln.product), "qty": ln.qty,
            "taxable_value": money(d(ln.qty) * d(ln.unit_cost)),
            "goods_kind": ln.goods_kind,
            "sent_directly_from_supplier": ch.origin == JobWorkChallan.Origin.DIRECT_FROM_SUPPLIER,
            "supplier_invoice": ch.supplier_invoice_ref,
        })
    settlements = JobWorkSettlement.objects.filter(
        company=company, reversed=False, settled_on__gte=date_from, settled_on__lte=date_to,
        receipt_line__receipt__status="POSTED",
    ).select_related(
        "challan_line__challan__order__supplier", "challan_line__product__unit", "receipt_line__receipt",
        "receipt_line__other_order",
    )
    for st in settlements:
        cl, rl = st.challan_line, st.receipt_line
        ch, sup = cl.challan, cl.challan.order.supplier
        base = {
            "orig_challan_no": ch.number, "orig_challan_date": ch.challan_date, "job_worker": sup.name,
            "gstin": sup.gstin or "", "product": cl.product.name, "hsn": cl.product.hsn_code, "uqc": _uqc(cl.product),
            "qty": st.qty, "receipt_no": rl.receipt.number, "receipt_date": rl.receipt.receipt_date,
        }
        if rl.kind in (K.PROCESSED, K.UNPROCESSED_RETURN, K.SCRAP_RETAINED):
            t5a.append({**base, "nature": {
                K.PROCESSED: "Processed goods received", K.UNPROCESSED_RETURN: "Unprocessed goods returned",
                K.SCRAP_RETAINED: "Loss, waste or scrap kept by the job worker",
            }[rl.kind], "loss_qty": rl.loss_qty if rl.kind == K.PROCESSED else (st.qty if rl.kind == K.SCRAP_RETAINED else 0)})
        elif rl.kind == K.SENT_TO_OTHER:
            t5b.append({**base, "sent_to": rl.other_order.supplier.name if rl.other_order_id else "",
                        "sent_to_gstin": (rl.other_order.supplier.gstin or "") if rl.other_order_id else ""})
        elif rl.kind == K.SUPPLIED_FROM_JW:
            t5c.append({**base, "invoice": rl.invoice_ref})
    return {
        "from": date_from, "to": date_to, "table4": t4, "table5a": t5a, "table5b": t5b, "table5c": t5c,
        "summary": {
            "sent_lines": len(t4), "sent_qty": sum((r["qty"] for r in t4), d(0)),
            "back_lines": len(t5a), "passed_on_lines": len(t5b), "supplied_lines": len(t5c),
            "unmatched": unmatched(company, date_from, date_to),
        },
    }


def unmatched(company, date_from, date_to) -> int:
    """Settlements in the period whose challan is outside ITC-04 (should be none)."""
    return JobWorkSettlement.objects.filter(
        company=company, reversed=False, settled_on__gte=date_from, settled_on__lte=date_to,
        challan_line__challan__status__in=["DRAFT", "REVERSED"],
    ).count()


def to_csv(tables: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    for key, title in (("table4", "Table 4: goods sent for job work"), ("table5a", "Table 5A: received back"),
                       ("table5b", "Table 5B: sent to another job worker"), ("table5c", "Table 5C: supplied from the job worker's premises")):
        rows = tables[key]
        w.writerow([title])
        if rows:
            w.writerow(list(rows[0].keys()))
            for r in rows:
                w.writerow([csv_safe(r[k]) for k in rows[0].keys()])
        w.writerow([])
    return out.getvalue()


@transaction.atomic
def prepare_filing(company, user, label: str, date_from: date, date_to: date) -> Itc04Filing:
    tables = build(company, date_from, date_to)
    filing, _ = Itc04Filing.objects.get_or_create(
        company=company, period_label=label, defaults={"from_date": date_from, "to_date": date_to, "created_by": user, "updated_by": user},
    )
    if filing.status == Itc04Filing.Status.FILED:
        raise rule("This period has been filed. It cannot be rebuilt.", "JW_ITC04_FILED")
    filing.summary = {k: (str(v) if not isinstance(v, (int, str)) else v) for k, v in tables["summary"].items()}
    filing.status = Itc04Filing.Status.EXPORTED
    filing.updated_by = user
    filing.save()
    return filing


@transaction.atomic
def mark_filed(filing, user, filed_on: date, acknowledgement: str = ""):
    filing = Itc04Filing.objects.select_for_update().get(pk=filing.pk)
    if filing.status == Itc04Filing.Status.DRAFT:
        raise rule("Export the return before marking it filed.", "JW_ITC04_NOT_EXPORTED")
    filing.status = Itc04Filing.Status.FILED
    filing.filed_on = filed_on
    filing.acknowledgement = acknowledgement[:64]
    filing.updated_by = user
    filing.save()
    return filing
