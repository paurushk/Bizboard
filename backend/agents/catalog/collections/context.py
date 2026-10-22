"""Collections Agent: deterministic facts, ranking, template drafts, validation.

Every number comes from the ledger and the invoice list. A model may only reword the template draft;
whatever it returns must pass the invented-number check, the tax-wording policy and a length check,
otherwise the template draft is used.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal

from django.conf import settings

from agents import numbers, tax_policy
from agents.error_codes import AGT_E_VALIDATION
from core.exceptions import BusinessRuleError

REMINDER = "REMINDER"
DEFAULT_WEIGHTS = {"amount": 1.0, "age": 0.3, "broken": 0.5, "late": 0.2}
SWEEP_TOP = 20
MAX_INVOICES_SHOWN = 10
MIN_TEXT, MAX_TEXT = 20, 1200

_KEY_CUSTOMER = re.compile(r"^(?:AR_CUSTOMER|AR_COLLECTION_RISK|AR_OVERDUE_\w+|PREDICTED_LATE_PAYMENT)[:](?:customer:)?(\d+)$")
_KEY_PROMISE = re.compile(r"^PROMISE_TO_PAY_DUE:(\d+)$")


# --- formatting --------------------------------------------------------------------------------
def inr(value) -> str:
    """Indian grouping, two decimals: 125000 -> 1,25,000.00"""
    q = Decimal(str(value)).quantize(Decimal("0.01"))
    sign = "-" if q < 0 else ""
    whole, frac = f"{abs(q):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}{whole}.{frac}"


def nice_date(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%d/%m/%Y")


# --- trigger parsing ---------------------------------------------------------------------------
def customer_ids_from_ref(company, ref: str) -> list[int]:
    """The customer a row points at. A promise row resolves to its customer. Empty for a sweep ref."""
    ref = (ref or "").strip()
    m = _KEY_CUSTOMER.match(ref)
    if m:
        return [int(m.group(1))]
    m = _KEY_PROMISE.match(ref)
    if m:
        from payments.models import PaymentPromise

        cid = PaymentPromise.objects.filter(company=company, pk=int(m.group(1))).values_list("customer_id", flat=True).first()
        return [cid] if cid else []
    return []


# --- facts per customer ------------------------------------------------------------------------
def _overdue_invoices(company, customer, as_of: date) -> list[dict]:
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice
    from sales.status_semantics import OPEN_SALES_STATUSES

    invoices = list(
        SalesInvoice.objects.filter(company=company, customer=customer, status__in=OPEN_SALES_STATUSES)
        .exclude(due_date__isnull=True).order_by("due_date", "id")
    )
    owed = LedgerService.bulk_sales_invoice_outstanding(company, invoice_ids=[i.id for i in invoices])
    rows = []
    for inv in invoices:
        amount = Decimal(str(owed.get(inv.id) or 0))
        days = (as_of - inv.due_date).days
        if amount > 0 and days > 0:
            rows.append({
                "invoice_id": inv.id, "number": inv.number or str(inv.pk), "due_date": inv.due_date.isoformat(),
                "outstanding": str(amount.quantize(Decimal("0.01"))), "days_overdue": days,
            })
    return rows


def _promise_facts(company, customer, as_of: date) -> dict:
    from payments.promise_to_pay import list_open_promises, promise_is_broken

    broken, upcoming = [], None
    for promise in list_open_promises(company, customer=customer):
        if promise_is_broken(promise, as_of=as_of):
            broken.append({
                "promise_id": promise.id, "promised_date": promise.promised_date.isoformat(),
                "amount": str(promise.promised_amount),
            })
        elif promise.promised_date >= as_of and upcoming is None:
            upcoming = {
                "promise_id": promise.id, "promised_date": promise.promised_date.isoformat(),
                "amount": str(promise.promised_amount) if promise.promised_amount is not None else None,
            }
    return {"broken": broken, "upcoming": upcoming}


def customer_facts(company, customer, as_of: date) -> dict | None:
    from payments.dunning import customer_risk_snapshot

    snap = customer_risk_snapshot(company, customer, as_of=as_of)
    overdue = Decimal(snap["overdue_amount"])
    if overdue <= 0:
        return None
    invoices = _overdue_invoices(company, customer, as_of)
    promises = _promise_facts(company, customer, as_of)
    oldest = invoices[0] if invoices else None
    broken_total = sum((Decimal(b["amount"]) for b in promises["broken"]), Decimal("0"))
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "overdue_amount": str(overdue.quantize(Decimal("0.01"))),
        "outstanding": snap["outstanding"],
        "invoice_count": len(invoices),
        "oldest_due_date": oldest["due_date"] if oldest else None,
        "oldest_days_overdue": oldest["days_overdue"] if oldest else 0,
        "avg_payment_delay_days": snap["average_payment_delay_days"],
        "collection_status": snap["collection_status"],
        "ageing": snap["ageing"],
        "invoices": invoices[:MAX_INVOICES_SHOWN],
        "broken_promises": promises["broken"],
        "broken_promise_total": str(broken_total),
        "upcoming_promise": promises["upcoming"],
        "dunning_opt_out": bool(snap.get("dunning_opt_out")),
    }


# --- ranking (rules; weights live in settings) -------------------------------------------------
def weights() -> dict:
    return {**DEFAULT_WEIGHTS, **getattr(settings, "AGENTS_COLLECTIONS_WEIGHTS", {})}


def rank_customers(items: list[dict]) -> list[dict]:
    """Highest priority first. Deterministic: ties break on customer id."""
    if not items:
        return []
    w = weights()

    def norm(key, conv=float):
        vals = [conv(i.get(key) or 0) for i in items]
        top = max(vals) or 1
        return {i["customer_id"]: v / top for i, v in zip(items, vals)}

    amount = norm("overdue_amount")
    age = norm("oldest_days_overdue")
    broken = norm("broken_promise_total")
    late = norm("avg_payment_delay_days", lambda v: max(float(v or 0), 0))

    def score(i):
        cid = i["customer_id"]
        return w["amount"] * amount[cid] + w["age"] * age[cid] + w["broken"] * broken[cid] + w["late"] * late[cid]

    return sorted(items, key=lambda i: (-score(i), i["customer_id"]))


def holdout(company, customer_id: int) -> bool:
    """Deterministic 20% holdout for outcome measurement. Only active when the company opts in (AGT-208)."""
    flags = company.feature_flags or {}
    return bool(flags.get("AGENT_COLLECTIONS_HOLDOUT")) and (hash_int(company.pk, customer_id) % 5 == 0)


def hash_int(*parts) -> int:
    import zlib

    return zlib.crc32(":".join(str(p) for p in parts).encode("utf-8"))


# --- templates ---------------------------------------------------------------------------------
def _tone(facts: dict) -> str:
    firm = facts["collection_status"] in ("overdue_severe", "stop_credit") or bool(facts["broken_promises"])
    return "firm" if firm else "polite"


def render_variants(facts: dict, company_name: str) -> dict[str, str]:
    name, amt = facts["customer_name"], inr(facts["overdue_amount"])
    n, oldest = facts["invoice_count"], facts["oldest_due_date"]
    when = nice_date(oldest) if oldest else None
    promise = ""
    promise_hi = ""
    if facts["broken_promises"]:
        b = facts["broken_promises"][0]
        promise = f"You had promised to pay ₹{inr(b['amount'])} by {nice_date(b['promised_date'])}. "
        promise_hi = f"आपने {nice_date(b['promised_date'])} तक ₹{inr(b['amount'])} देने का वादा किया था। "
    inv_en = f" across {n} invoice{'s' if n != 1 else ''}, the oldest due on {when}" if when else ""
    inv_hi = f" ({n} बिल, सबसे पुराना {when} को देय)" if when else ""
    out = {
        "en:polite": (
            f"Dear {name},\n\nThis is a gentle reminder that ₹{amt} is overdue on your account with {company_name}{inv_en}. "
            f"{promise}Please arrange the payment at your earliest convenience, or let us know when we can expect it.\n\n"
            f"Thank you,\n{company_name}"
        ),
        "en:firm": (
            f"Dear {name},\n\nYour account with {company_name} has ₹{amt} overdue{inv_en}. {promise}"
            f"Please clear this payment this week, or tell us a firm date by which you will pay.\n\n{company_name}"
        ),
        "hi:polite": (
            f"आदरणीय {name},\n\n{company_name} के साथ आपके खाते में ₹{amt} की राशि बकाया है{inv_hi}। "
            f"{promise_hi}कृपया जल्द से जल्द भुगतान करें, या बताएँ कि भुगतान कब तक होगा।\n\nधन्यवाद,\n{company_name}"
        ),
        "hi:firm": (
            f"आदरणीय {name},\n\n{company_name} के साथ आपके खाते में ₹{amt} बकाया है{inv_hi}। {promise_hi}"
            f"कृपया इसी सप्ताह भुगतान करें, या भुगतान की पक्की तारीख बताएँ।\n\n{company_name}"
        ),
    }
    return out


def _evidence(facts: dict, company_name: str) -> list[dict]:
    cid = facts["customer_id"]
    ev = [{
        "type": "customer", "id": cid, "label": f"{facts['customer_name']}: ₹{inr(facts['overdue_amount'])} overdue",
        "href": f"/reports/customer-ledger?customer={cid}", "fact": facts["overdue_amount"],
    }]
    for inv in facts["invoices"][:5]:
        ev.append({
            "type": "invoice", "id": inv["invoice_id"],
            "label": f"{inv['number']}: ₹{inr(inv['outstanding'])}, {inv['days_overdue']} days overdue",
            "href": f"/sales/history/{inv['invoice_id']}", "fact": inv["outstanding"],
        })
    for b in facts["broken_promises"][:2]:
        ev.append({
            "type": "promise", "id": b["promise_id"],
            "label": f"Promised ₹{inr(b['amount'])} by {nice_date(b['promised_date'])}", "href": "/payments/collections",
            "fact": b["amount"],
        })
    if facts["dunning_opt_out"]:
        ev.append({"type": "fact", "id": "opt_out", "label": "Customer opted out of automatic reminders", "fact": True})
    return ev


def draft_for(facts: dict, company_name: str, dedupe_key: str, *, text_override: str | None = None) -> dict:
    variants = render_variants(facts, company_name)
    tone = _tone(facts)
    language = "en"
    key = f"{language}:{tone}"
    if text_override:
        variants[key] = text_override
    return {
        "kind": REMINDER,
        "title": f"Reminder: {facts['customer_name']} (₹{inr(facts['overdue_amount'])})",
        "dedupe_key": dedupe_key,
        "payload": {
            "customer_id": facts["customer_id"], "customer_name": facts["customer_name"], "text": variants[key],
            "language": language, "tone": tone, "total_overdue": facts["overdue_amount"], "variants": variants,
        },
        "evidence": _evidence(facts, company_name),
    }


# --- spec hooks --------------------------------------------------------------------------------
def build_context(tctx) -> dict:
    from masters.models import Customer

    company, run, as_of = tctx.company, tctx.run, tctx.as_of
    ids = customer_ids_from_ref(company, run.trigger_ref)
    customers: list[dict] = []
    if ids:
        for cust in Customer.objects.filter(company=company, pk__in=ids):
            facts = customer_facts(company, cust, as_of)
            if facts:
                customers.append(facts)
        return {"facts": {"company_name": company.name, "customers": customers}, "rules_only": False}
    # Scheduled sweep: rank the customers who owe the most overdue money; drafts are template-only.
    from payments.dunning import list_customer_risk

    top = SWEEP_TOP
    for snap in list_customer_risk(company, as_of=as_of, limit=top * 3):
        if Decimal(snap["overdue_amount"]) <= 0:
            continue
        cust = Customer.objects.filter(company=company, pk=snap["customer_id"]).first()
        facts = customer_facts(company, cust, as_of) if cust else None
        if facts is None or facts["dunning_opt_out"] or holdout(company, cust.id):
            continue
        customers.append(facts)
    customers = rank_customers(customers)[:top]
    return {"facts": {"company_name": company.name, "customers": customers}, "rules_only": True}


def _dedupe_key(tctx, facts: dict) -> str:
    ref = (tctx.run.trigger_ref or "").strip()
    if _KEY_CUSTOMER.match(ref) or _KEY_PROMISE.match(ref):
        return ref
    return f"AR_CUSTOMER:{facts['customer_id']}"


def rules_only(tctx, context) -> list[dict]:
    name = context["facts"]["company_name"]
    return [draft_for(f, name, _dedupe_key(tctx, f)) for f in context["facts"]["customers"]]


def parse_final(tctx, context, text: str) -> list[dict]:
    """Model output replaces the default variant of the single customer's draft. Anything else is a ValueError."""
    customers = context["facts"]["customers"]
    if len(customers) != 1:
        raise ValueError("the model is only used for a single customer")
    data = json.loads(text)
    reply = data["text"]
    if not isinstance(reply, str):
        raise ValueError("text must be a string")
    return [draft_for(customers[0], context["facts"]["company_name"], _dedupe_key(tctx, customers[0]), text_override=reply.strip())]


def validate(tctx, context, drafts: list[dict]) -> None:
    known = {c["customer_id"] for c in context["facts"]["customers"]}
    for d in drafts:
        payload = d["payload"]
        if payload["customer_id"] not in known:
            raise BusinessRuleError("Draft names a customer that is not in the facts.", code=AGT_E_VALIDATION)
        facts = next(c for c in context["facts"]["customers"] if c["customer_id"] == payload["customer_id"])
        for variant in {payload["text"], *payload.get("variants", {}).values()}:
            if not (MIN_TEXT <= len(variant) <= MAX_TEXT):
                raise BusinessRuleError("Draft text has an unreasonable length.", code=AGT_E_VALIDATION)
            if tax_policy.violates(variant):
                raise BusinessRuleError("Draft contains tax advice.", code=AGT_E_VALIDATION)
            bad = numbers.invented_numbers(variant, [facts, context["facts"]["company_name"]], cited_count=len(d["evidence"]))
            if bad:
                raise BusinessRuleError(f"Draft contains numbers that are not in the books: {bad}", code=AGT_E_VALIDATION)
        if not d["evidence"]:
            raise BusinessRuleError("Draft has no evidence.", code=AGT_E_VALIDATION)


def still_open(company, dedupe_keys):
    """Keys whose condition still holds. Keys we do not recognise are kept (never cancel on a guess)."""
    from decimal import Decimal as D

    from masters.models import Customer
    from payments.dunning import customer_risk_snapshot
    from payments.models import PaymentPromise

    open_keys = set()
    for key in dedupe_keys:
        pm = _KEY_PROMISE.match(key)
        cm = _KEY_CUSTOMER.match(key)
        if pm:
            if PaymentPromise.objects.filter(company=company, pk=int(pm.group(1)), resolved=False).exists():
                open_keys.add(key)
        elif cm:
            cust = Customer.objects.filter(company=company, pk=int(cm.group(1))).first()
            if cust and D(customer_risk_snapshot(company, cust)["overdue_amount"]) > 0:
                open_keys.add(key)
        else:
            open_keys.add(key)
    return open_keys
