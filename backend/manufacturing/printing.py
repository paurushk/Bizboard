"""Print-ready pages for the shop: a work order sheet and a material issue slip (MFG-X1).

Plain HTML with a print stylesheet, no costs on the page (the floor sees quantities, not money).
The web opens the page in a new window and the browser prints it.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.html import escape

STYLE = """
body{font-family:Arial,Helvetica,sans-serif;margin:32px;color:#111}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:22px 0 8px}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #999;padding:6px 8px;text-align:left;font-size:13px}
th{background:#eee} td.n,th.n{text-align:right}
.meta td{border:0;padding:2px 14px 2px 0} .sign{margin-top:56px;display:flex;justify-content:space-between}
@media print{body{margin:12mm}}
"""


def _q(value) -> str:
    return f"{Decimal(str(value)).normalize():f}"


def _page(title: str, company, body: str) -> str:
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"<style>{STYLE}</style></head><body><h1>{escape(company.name)}</h1><div>{escape(title)}</div>{body}</body></html>"
    )


def work_order_sheet(wo) -> str:
    lines = "".join(
        f"<tr><td>{escape(ln.component.name)}</td><td class='n'>{_q(ln.qty)}</td>"
        f"<td class='n'>{_q(ln.qty_issued)}</td><td class='n'>{_q(ln.qty_returned)}</td><td></td></tr>"
        for ln in wo.component_lines.select_related("component")
    )
    outs = "".join(
        f"<tr><td>{escape(o.product.name)}</td><td>{escape(o.get_kind_display())}</td><td class='n'>{_q(o.qty)}</td></tr>"
        for o in wo.planned_outputs.select_related("product")
    )
    steps = "".join(
        f"<tr><td>{c.sequence}</td><td>{escape(c.name)}</td><td>{escape(c.work_centre.code)}</td>"
        f"<td class='n'>{_q(c.planned_minutes)}</td><td class='n'></td></tr>"
        for c in wo.job_cards.select_related("work_centre").order_by("sequence")
    )
    body = f"""
<h2>{escape(wo.product.name if wo.product_id else '')} &times; {_q(wo.qty)}</h2>
<table class="meta">
<tr><td>Work order</td><td>{escape(wo.number)}</td><td>Status</td><td>{escape(wo.get_status_display())}</td></tr>
<tr><td>Due</td><td>{wo.due_date or '-'}</td><td>Priority</td><td>{wo.priority}</td></tr>
<tr><td>Batch</td><td>{escape(wo.batch_no or '-')}</td><td>Notes</td><td>{escape(wo.notes or '')}</td></tr>
</table>
<h2>Material</h2>
<table><tr><th>Material</th><th class="n">Needed</th><th class="n">Issued</th><th class="n">Returned</th><th>Checked</th></tr>{lines}</table>
{f'<h2>Also comes out</h2><table><tr><th>Item</th><th>Kind</th><th class="n">Quantity</th></tr>{outs}</table>' if outs else ''}
{f'<h2>Steps</h2><table><tr><th>No.</th><th>Step</th><th>Work centre</th><th class="n">Minutes planned</th><th class="n">Done</th></tr>{steps}</table>' if steps else ''}
<div class="sign"><div>Issued by ______________</div><div>Received by ______________</div><div>Checked by ______________</div></div>
"""
    return _page("Work order", wo.company, body)


def issue_slip(issue) -> str:
    rows = "".join(
        f"<tr><td>{escape(ln.component.name)}</td><td>{escape(ln.warehouse.name)}</td>"
        f"<td>{escape(ln.batch.batch_no) if ln.batch_id else '-'}</td><td class='n'>{_q(ln.qty)}</td>"
        f"<td>{'Extra' if ln.is_extra else ''}</td></tr>"
        for ln in issue.lines.select_related("component", "warehouse", "batch")
    )
    body = f"""
<h2>Material issue {escape(issue.number)}</h2>
<table class="meta">
<tr><td>Work order</td><td>{escape(issue.work_order.number)}</td><td>Date</td><td>{issue.doc_date or '-'}</td></tr>
<tr><td>Status</td><td>{escape(issue.get_status_display())}</td><td>Notes</td><td>{escape(issue.notes or '')}</td></tr>
</table>
<h2>Handed over</h2>
<table><tr><th>Material</th><th>From</th><th>Batch</th><th class="n">Quantity</th><th></th></tr>{rows}</table>
<div class="sign"><div>Issued by ______________</div><div>Received by ______________</div></div>
"""
    return _page("Material issue slip", issue.company, body)


LABEL_STYLE = """
body{font-family:Arial,Helvetica,sans-serif;margin:0;color:#111}
.label{box-sizing:border-box;width:100mm;height:50mm;padding:4mm;border:1px dashed #999;margin:4mm;page-break-after:always;overflow:hidden}
.label h1{font-size:15px;margin:0 0 2mm} .label .batch{font-size:22px;font-weight:bold;letter-spacing:1px;margin:2mm 0}
.label table{border-collapse:collapse;width:100%} .label td{font-size:12px;padding:1px 6px 1px 0}
@media print{.label{border:0;margin:0}}
"""


def batch_labels(receipt, copies: int = 1) -> str:
    """One label per good batch on a production receipt: item, batch, dates, quantity, the work order it came from."""
    copies = max(1, min(int(copies or 1), 50))
    items = []
    for ln in receipt.lines.select_related("product", "batch").filter(batch__isnull=False, qty_good__gt=0):
        lot = ln.batch
        sku = f"<tr><td>Item code</td><td>{escape(ln.product.sku)}</td></tr>" if getattr(ln.product, "sku", "") else ""
        items.append(
            f'<div class="label"><h1>{escape(ln.product.name)}</h1>'
            f'<div class="batch">{escape(lot.batch_no)}</div><table>{sku}'
            f"<tr><td>Quantity</td><td>{_q(ln.qty_good)}</td></tr>"
            f"<tr><td>Made on</td><td>{lot.manufacturing_date or receipt.mfg_date or receipt.doc_date or '-'}</td></tr>"
            f"<tr><td>Use before</td><td>{lot.expiry_date or '-'}</td></tr>"
            f"<tr><td>Work order</td><td>{escape(receipt.work_order.number)}</td></tr></table></div>"
        )
    labels = "".join(items * copies) or "<p>This receipt has no batch to label.</p>"
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Batch label {escape(receipt.number)}</title>'
        f"<style>{LABEL_STYLE}</style></head><body>{labels}</body></html>"
    )
