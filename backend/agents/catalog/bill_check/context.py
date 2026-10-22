"""Bill Check Agent: compare draft purchase bills with their PO and goods receipt, draft a supplier query.

Facts come from ``compare.compare_bill``. A model may only reword the template message for a single bill; the
result must pass the invented-number, tax-wording and length checks, otherwise the template is used.
"""

from __future__ import annotations

import hashlib
import json
import re

from agents import numbers, tax_policy
from agents.error_codes import AGT_E_VALIDATION
from core.exceptions import BusinessRuleError

from .compare import compare_bill

KIND = "SUPPLIER_QUERY"
NOTE_KIND = "BILL_REVIEW_NOTE"
_KEY = re.compile(r"^(?:PURCHASE_BILL|BILL_CHECK|BILL_NOTE):(\d+)$")
SWEEP_TOP = 20
MIN_TEXT, MAX_TEXT = 40, 1200
MAX_LISTED = 8      # differences written into the message; the table beside it lists the rest
MAX_ROWS, MAX_NOTES = 200, 20


def bill_id_from_ref(ref: str) -> int | None:
    m = _KEY.match((ref or "").strip())
    return int(m.group(1)) if m else None


def digest_of(findings: list[dict]) -> str:
    blob = json.dumps([[f["code"], f["text"]] for f in findings], sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def bill_facts(invoice) -> dict | None:
    result = compare_bill(invoice)
    findings = result["findings"]
    to_supplier = [f for f in findings if f["to_supplier"]]
    # A missing goods receipt alone is not worth a draft on every purchase-order bill; it rides along with other findings.
    worth_a_draft = [f for f in findings if f["to_supplier"] or f["code"] != "NO_GRN"]
    if not worth_a_draft:
        return None
    return {
        "bill_id": invoice.pk, "bill_number": invoice.supplier_bill_number or invoice.number or f"draft {invoice.pk}",
        "supplier_id": invoice.supplier_id, "supplier_name": invoice.supplier.name,
        "differences": [f["text"] for f in to_supplier],
        "internal_notes": [f["text"][:300] for f in findings if not f["to_supplier"]][:MAX_NOTES],
        "rows": result["rows"][:MAX_ROWS], "findings_digest": digest_of(findings),
    }


def note_draft_for(facts: dict) -> dict:
    return {
        "kind": NOTE_KIND,
        "title": f"Check bill {facts['bill_number']} ({len(facts['internal_notes'])} note(s) for you)",
        "dedupe_key": f"BILL_NOTE:{facts['bill_id']}",
        "payload": {
            "bill_id": facts["bill_id"], "bill_number": facts["bill_number"], "supplier_name": facts["supplier_name"],
            "internal_notes": facts["internal_notes"], "rows": facts["rows"], "findings_digest": facts["findings_digest"],
        },
        "evidence": [
            {"type": "invoice", "id": facts["bill_id"], "label": f"Draft bill {facts['bill_number']}", "href": f"/purchases/{facts['bill_id']}"},
            *[{"type": "fact", "id": f"n{i}", "label": t} for i, t in enumerate(facts["internal_notes"][:10])],
        ],
    }


def render_text(facts: dict, company_name: str) -> str:
    listed = facts["differences"][:MAX_LISTED]
    items = "\n".join(f"- {t[:160]}" for t in listed)
    more = len(facts["differences"]) - len(listed)
    if more > 0:
        items += f"\n- and {more} more difference(s) that we will share separately"
    return (
        f"Dear {facts['supplier_name']},\n\nWhile checking your bill {facts['bill_number']} we found these differences "
        f"with our records:\n{items}\n\nPlease review and send a corrected bill, or tell us if our records are wrong.\n\n"
        f"Thank you,\n{company_name}"
    )


def draft_for(facts: dict, company_name: str, *, text_override: str | None = None) -> dict:
    return {
        "kind": KIND,
        "title": f"Query {facts['supplier_name']} about bill {facts['bill_number']}",
        "dedupe_key": f"BILL_CHECK:{facts['bill_id']}",
        "payload": {
            "supplier_id": facts["supplier_id"], "supplier_name": facts["supplier_name"], "bill_id": facts["bill_id"],
            "bill_number": facts["bill_number"], "text": text_override or render_text(facts, company_name),
            "internal_notes": facts["internal_notes"], "rows": facts["rows"], "findings_digest": facts["findings_digest"],
        },
        "evidence": [
            {"type": "invoice", "id": facts["bill_id"], "label": f"Draft bill {facts['bill_number']}", "href": f"/purchases/{facts['bill_id']}"},
            *[{"type": "fact", "id": f"d{i}", "label": t} for i, t in enumerate(facts["differences"][:10])],
        ],
    }


def build_context(tctx) -> dict:
    from purchases.models import PurchaseInvoice

    company = tctx.company
    bill_id = bill_id_from_ref(tctx.run.trigger_ref)
    qs = PurchaseInvoice.objects.filter(company=company, status=PurchaseInvoice.Status.DRAFT).select_related("supplier")
    if bill_id:
        qs = qs.filter(pk=bill_id)
    else:
        qs = qs.order_by("-id")[: SWEEP_TOP * 3]
    bills = []
    for inv in qs:
        facts = bill_facts(inv)
        if facts:
            bills.append(facts)
    bills = bills[:SWEEP_TOP]
    if bill_id and not qs:
        raise BusinessRuleError("That bill is not a draft any more.", code=AGT_E_VALIDATION)
    return {"facts": {"company_name": company.name, "bills": bills}, "rules_only": bill_id is None}


def rules_only(tctx, context) -> list[dict]:
    return [
        draft_for(b, context["facts"]["company_name"]) if b["differences"] else note_draft_for(b)
        for b in context["facts"]["bills"]
    ]


def parse_final(tctx, context, text: str) -> list[dict]:
    bills = context["facts"]["bills"]
    if len(bills) != 1 or not bills[0]["differences"]:
        raise ValueError("the model is only used for a single bill with something to tell the supplier")
    reply = json.loads(text)["text"]
    if not isinstance(reply, str):
        raise ValueError("text must be a string")
    return [draft_for(bills[0], context["facts"]["company_name"], text_override=reply.strip())]


def validate(tctx, context, drafts: list[dict]) -> None:
    by_id = {b["bill_id"]: b for b in context["facts"]["bills"]}
    for d in drafts:
        payload = d["payload"]
        facts = by_id.get(payload["bill_id"])
        if facts is None:
            raise BusinessRuleError("Draft names a bill that is not in the facts.", code=AGT_E_VALIDATION)
        if d["kind"] == NOTE_KIND:
            continue
        text = payload["text"]
        if not (MIN_TEXT <= len(text) <= MAX_TEXT):
            raise BusinessRuleError("Draft text has an unreasonable length.", code=AGT_E_VALIDATION)
        if tax_policy.violates(text):
            raise BusinessRuleError("Draft contains tax advice.", code=AGT_E_VALIDATION)
        bad = numbers.invented_numbers(text, [facts, context["facts"]["company_name"]], cited_count=len(facts["differences"]))
        if bad:
            raise BusinessRuleError(f"Draft contains numbers that are not in the books: {bad}", code=AGT_E_VALIDATION)
        missing = [t for t in facts["differences"][:MAX_LISTED] if t.split(":")[0] not in text and t[:30] not in text]
        if missing:
            raise BusinessRuleError("Draft leaves out a difference.", code=AGT_E_VALIDATION)


def still_open(company, dedupe_keys):
    from purchases.models import PurchaseInvoice

    out = set()
    for key in dedupe_keys:
        m = _KEY.match(key)
        if not m:
            out.add(key)
        elif PurchaseInvoice.objects.filter(company=company, pk=int(m.group(1)), status=PurchaseInvoice.Status.DRAFT).exists():
            out.add(key)
    return out
