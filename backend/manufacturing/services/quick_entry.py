"""Quick production entry (MFG-12): record a day's production in one step.

One transaction makes the work order, issues the materials, receives the output and closes the
order, through the same services the long path uses, so the books come out identical.
"""


from django.db import transaction

from manufacturing.models import WorkOrder

from . import flow
from . import bom as bom_svc
from .common import next_number, qty3, rule
from .issue import create_issue, post_issue
from .receipt import create_receipt, post_receipt


@transaction.atomic
def quick_production(company, user, *, product, qty, doc_date=None, customer=None, warehouse=None,
                     fg_warehouse=None, batch_no="", exp_date=None, mfg_date=None, components=None,
                     notes="", can_backdate=True, is_manager=True) -> WorkOrder:
    """Make, issue, receive and close a work order in one go.

    ``components`` maps a component product (or id) to the quantity actually used; anything not
    named uses the planned quantity.
    """
    from .legacy import _snapshot_bom

    qty = qty3(qty)
    if qty <= 0:
        raise rule("Enter how many units were made.", "MFG_BAD_QTY")
    bom = bom_svc.resolve_bom(company, product, doc_date, customer)
    wo = WorkOrder.objects.create(
        company=company, bom=bom, qty=qty, issue_mode=WorkOrder.IssueMode.SEPARATE,
        number=next_number(company, "mfg_wo", "WO"), warehouse=warehouse, fg_warehouse=fg_warehouse,
        batch_no=batch_no or "", exp_date=exp_date, mfg_date=mfg_date,
        notes=(notes or "")[:500], created_by=user, updated_by=user,
    )
    _snapshot_bom(wo)
    bom_svc.lock_bom(bom)
    wo = flow.release_separate(wo, user, can_backdate=can_backdate)

    actual = {}
    for key, value in (components or {}).items():
        actual[getattr(key, "pk", key)] = qty3(value)
    lines = []
    for wl in wo.component_lines.select_related("component"):
        if wl.principal_supplied:
            continue
        used = actual.pop(wl.component_id, wl.qty)
        if used <= 0:
            continue
        row = {"wo_line": wl, "qty": used}
        if used > wl.qty:
            row["extra_reason"] = "Entered in quick production"
        lines.append(row)
    if actual:
        raise rule("One of the materials is not part of this recipe.", "MFG_BAD_WO_LINE")
    if not lines:
        raise rule("There is nothing to issue.", "MFG_NOTHING_TO_ISSUE")
    issue = create_issue(wo, user, lines, doc_date=doc_date)
    post_issue(issue, user, can_backdate=can_backdate, is_manager=is_manager)

    receipt = create_receipt(
        wo, user, {
            "doc_date": doc_date, "is_final": True, "batch_no": batch_no, "exp_date": exp_date,
            "mfg_date": mfg_date,
        },
    )
    post_receipt(receipt, user, can_backdate=can_backdate, is_manager=is_manager)
    wo.refresh_from_db()
    # The order is complete once its final receipt posts. A short run is closed the same way.
    if wo.status != WorkOrder.Status.COMPLETED:
        wo = flow.complete_separate(wo, user, can_backdate=can_backdate)
    return flow.close_work_order(wo, user, can_backdate=can_backdate)
