"""Tool-grounded NL assistant (Phase 6.4)."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.exceptions import BusinessRuleError
from reporting.services import ReportService

from .models import AiUsageLedger, AssistantMessage, AssistantThread
from .services import (
    build_growth_hints,
    compute_health_score,
    forecast_cashflow,
    generate_daily_summary,
    upsert_alerts,
)

PROMPT_VERSION = "assistant-v1"
TOOLS_VERSION = "tools-v1"

# Confirm path allowlist only — never money-moving / irreversible posts without re-auth.
# Existing proposals use snake_case reminder types; uppercase names are reserved for
# future safe UX actions (draft/nav/report) and are not money moves.
CONFIRMABLE_ACTION_TYPES = frozenset({
    "send_reminder",
    "copy_reminder",
    "CREATE_DRAFT_INVOICE",
    "NAVIGATE",
    "SHOW_REPORT",
})
MONEY_MOVING_ACTION_TYPES = frozenset({
    "COMPLETE_INVOICE",
    "RECORD_PAYMENT",
    "CANCEL_INVOICE",
    "COMPLETE_RETURN",
    "CREATE_PAYMENT",
    "ALLOCATE_PAYMENT",
    "POST_JOURNAL",
})

TAX_REFUSAL = (
    "I cannot give tax rates, place-of-supply, or GSTR filing advice. "
    "Use Reports → GST Health / GSTR aids, or ask your CA."
)

TAX_PATTERNS = re.compile(
    r"\b("
    r"gstr|gst\s*rate|gst\s*return|place of supply|hsn\s*(code|rate)?|"
    r"file\s*(gst|gstr|return)|tax\s*liability|input\s*tax|itc\b|"
    r"cgst|sgst|igst|cess|einvoice|e-?invoice|e-?way|rcm|reverse\s*charge|"
    r"composition\s*scheme|gstin\s*valid|"
    r"how\s+much\s+(gst|tax)|what\s+(gst|tax)\s+rate|should\s+i\s+charge|"
    r"taxable\s+value|output\s+tax|input\s+credit|gstr-?[123]|nil[\s-]?rated|"
    r"exempt\s+(supply|sale)|inter[\s-]?state|intra[\s-]?state|"
    r"tds|tcs|section\s*9|gst\s*portal|filing\s*due|"
    r"tax\s*rate\s*advice|claim\s*itc|avail\s*itc|itc\s*claim|"
    r"gst\s*calculation|calculate\s*gst|gst\s*amount|"
    r"rate\s+for\s+\w+|sold\s+to\s+\w+|applicable\s+(gst|tax|rate)|"
    r"what\s+rate|which\s+rate|gst\s+on\s+\w+|charge\s+gst|"
    r"hsn\s+for|tax\s+for\s+\w+|rate\s+in\s+\w+"
    r")\b|"
    r"(जी.?एस.?टी|कर|टैक्स|कर\s*दर|इनपुट\s*कर\s*क्रेडिट)",
    re.I,
)

_INDIRECT_TAX_HINTS = re.compile(
    r"(sold to|ship(?:ped)? to|deliver(?:ed)? to|pos\b|place of supply|"
    r"pune|mumbai|delhi|chennai|kolkata|bengaluru|bangalore|hyderabad|"
    r"maharashtra|karnataka|tamil nadu|gujarat|rajasthan|kerala|"
    r"\bhsn\b|\bsac\b|soap|fmcg|rate)",
    re.I,
)


def _looks_like_tax_question(text: str) -> bool:
    blob = text or ""
    if TAX_PATTERNS.search(blob):
        return True
    lowered = blob.lower()
    asks_rate = bool(re.search(r"\b(rate|%|percent|gst|tax|hsn|sac)\b", lowered))
    has_geo_or_sku = bool(_INDIRECT_TAX_HINTS.search(blob))
    return asks_rate and has_geo_or_sku

# BB-000488: strip residual tax-advice phrases from model output.
TAX_OUTPUT_STRIP = re.compile(
    r"(?i)\b("
    r"you should (file|charge|claim)|recommend(ed)? (gst|gstr|itc|tax)|"
    r"(cgst|sgst|igst|itc)\s+(rate|claim|credit)|"
    r"place of supply (is|should)|gstr-?[1239]\s+(due|filing)|"
    r"tax rate (is|should|would)|charge\s+\d+\s*%\s*gst"
    r")[^\n\.]*[\.\n]?",
)


def _month_token_usage(company) -> int:
    start = timezone.localdate().replace(day=1)
    rows = AiUsageLedger.objects.filter(company=company, created_at__date__gte=start)
    return sum((r.tokens_in + r.tokens_out) for r in rows)


def assert_within_budget(company):
    budget = company.ai_monthly_token_budget
    if budget is None:
        budget = int(getattr(settings, "AI_MONTHLY_TOKEN_BUDGET_DEFAULT", 100_000) or 100_000)
    used = _month_token_usage(company)
    if used >= budget:
        raise BusinessRuleError(
            f"AI monthly token budget reached ({used}/{budget}). Contact your owner to raise the limit."
        )
    # BB-000531: warn owner once per month at 80% utilization.
    if budget > 0 and used >= int(budget * 0.8):
        _maybe_alert_budget_threshold(company, used, budget)


def _maybe_alert_budget_threshold(company, used: int, budget: int) -> None:
    from django.core.cache import cache

    month_key = timezone.localdate().strftime("%Y-%m")
    cache_key = f"ai_budget_alert:{company.id}:{month_key}"
    if cache.get(cache_key):
        return
    try:
        from accounts.models import CompanyUser
        from core.models import Notification
        from core.services.notifications import NotificationService

        owner = (
            CompanyUser.objects.filter(company=company, role="OWNER", is_active=True)
            .select_related("user")
            .order_by("id")
            .first()
        )
        if owner is None or not owner.user.email:
            return
        pct = int((used / budget) * 100) if budget else 100
        NotificationService.send(
            company=company,
            channel=Notification.Channel.EMAIL,
            recipient=owner.user.email,
            subject="Bizboard AI budget at 80%",
            body=(
                f"AI token usage for {company.name} is at {pct}% ({used}/{budget}) "
                "this month. Consider raising ai_monthly_token_budget or disabling AI features."
            ),
            user=owner.user,
        )
        cache.set(cache_key, 1, 60 * 60 * 24 * 35)
    except Exception:
        return


def record_usage(company, *, feature, tokens_in=0, tokens_out=0, model_name=""):
    AiUsageLedger.objects.create(
        company=company,
        feature=feature,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model_name=model_name or "",
        prompt_version=PROMPT_VERSION,
    )


class ToolExecutor:
    """Company-scoped read tools — fail closed on wrong company."""

    def __init__(self, company):
        self.company = company

    def run(self, name: str, args: dict | None = None) -> dict:
        args = args or {}
        # Ignore any client-supplied company_id
        args.pop("company_id", None)
        args.pop("company", None)
        fn = getattr(self, f"tool_{name}", None)
        if not fn:
            raise BusinessRuleError(f"Unknown tool: {name}")
        return fn(**args)

    def tool_get_daily_summary(self, date: str | None = None):
        from datetime import date as date_cls

        d = date_cls.fromisoformat(date) if date else None
        s = generate_daily_summary(self.company, for_date=d)
        return {
            "summary_date": s.summary_date.isoformat(),
            "kpis": s.kpis,
            "narrative": s.narrative,
            "alert_codes": s.alert_codes,
            "citation": {"path": "/insights", "label": "Daily summary"},
        }

    def tool_get_health_score(self):
        data = compute_health_score(self.company)
        return {
            **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in data.items() if k != "factors"},
            "factors": data["factors"],
            "citation": {"path": "/insights/health", "label": "Business health"},
        }

    def tool_get_cashflow_forecast(self, horizon: int = 14):
        data = forecast_cashflow(self.company, horizon=int(horizon or 14), persist=False)
        return {**data, "citation": {"path": "/insights/cashflow", "label": "Cashflow forecast"}}

    def tool_get_sales_totals(self, days: int = 30):
        from datetime import timedelta

        days = max(1, min(int(days or 30), 365))
        end = timezone.localdate()
        start = end - timedelta(days=days - 1)
        from sales.models import SalesInvoice

        from sales.models import SalesReturn

        sales = (
            SalesInvoice.objects.filter(
                company=self.company,
                status=SalesInvoice.Status.COMPLETED,
                invoice_date__gte=start,
                invoice_date__lte=end,
            ).aggregate(total=Coalesce(Sum("grand_total"), Decimal("0")))["total"]
            or Decimal("0")
        )
        returns = (
            SalesReturn.objects.filter(
                company=self.company,
                status=SalesReturn.Status.COMPLETED,
                return_date__gte=start,
                return_date__lte=end,
            ).aggregate(total=Coalesce(Sum("grand_total"), Decimal("0")))["total"]
            or Decimal("0")
        )
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "total": str(sales - returns),
            "citation": {"path": "/reports/sales", "label": "Sales register"},
        }

    def tool_get_receivables_aging(self):
        aging = ReportService.receivables_aging(self.company)
        return {
            "aging": {k: str(v) for k, v in aging.items()},
            "citation": {"path": "/", "label": "Dashboard aging"},
        }

    def tool_get_payables_aging(self):
        buckets = ReportService.payables_aging(self.company)
        payables = ReportService._company_payables(self.company)
        return {
            "aging": {k: str(v) for k, v in buckets.items()},
            "payables_total": str(payables),
            "citation": {"path": "/reports/supplier-ledger", "label": "Supplier ledger"},
        }

    def tool_list_business_alerts(self):
        alerts = upsert_alerts(self.company)
        open_alerts = [
            {
                "code": a.code,
                "severity": a.severity,
                "message": a.message,
                "cta_path": a.cta_path,
            }
            for a in alerts
            if a.status == a.Status.OPEN
        ]
        return {
            "alerts": open_alerts,
            "citation": {"path": "/insights/alerts", "label": "Business alerts"},
        }

    def tool_list_growth_hints(self):
        return {
            "hints": build_growth_hints(self.company),
            "citation": {"path": "/insights/health", "label": "Growth hints"},
        }

    def tool_get_customer_outstanding(self, customer_id: int | None = None, customer_name: str | None = None):
        from ledgers.services import LedgerService
        from masters.models import Customer

        qs = Customer.objects.filter(company=self.company)
        if customer_id:
            cust = qs.filter(id=customer_id).first()
        elif customer_name:
            cust = qs.filter(name__icontains=customer_name).first()
        else:
            raise BusinessRuleError("customer_id or customer_name required")
        if not cust:
            raise BusinessRuleError("Customer not found in this company.")
        outstanding = LedgerService.customer_outstanding(self.company, cust)
        return {
            "customer_id": cust.id,
            "customer_name": cust.name,
            "outstanding": str(outstanding),
            "citation": {"path": "/reports/customer-ledger", "label": cust.name},
        }

    def tool_search_documents(self, q: str = ""):
        from masters.models import Customer, Product, Supplier
        from purchases.models import PurchaseInvoice
        from sales.models import SalesInvoice

        q = (q or "").strip()
        results = []
        if q:
            for c in Customer.objects.filter(company=self.company, name__icontains=q)[:5]:
                results.append({"type": "customer", "id": c.id, "label": c.name, "path": "/sales/customers"})
            for s in Supplier.objects.filter(company=self.company, name__icontains=q)[:5]:
                results.append({"type": "supplier", "id": s.id, "label": s.name, "path": "/purchases/suppliers"})
            for p in Product.objects.filter(company=self.company, name__icontains=q)[:5]:
                results.append({"type": "product", "id": p.id, "label": p.name, "path": "/inventory/products"})
            for inv in SalesInvoice.objects.filter(company=self.company, number__icontains=q)[:5]:
                results.append({
                    "type": "sales_invoice", "id": inv.id, "label": inv.number or str(inv.id),
                    "path": f"/sales/history/{inv.id}",
                })
            for inv in PurchaseInvoice.objects.filter(company=self.company, number__icontains=q)[:5]:
                results.append({
                    "type": "purchase_invoice", "id": inv.id, "label": inv.number or str(inv.id),
                    "path": f"/purchases/history/{inv.id}",
                })
        return {
            "results": results,
            "citation": {"path": "/", "label": "Search"},
        }

    def tool_draft_payment_reminder(self, customer_id: int | None = None, customer_name: str | None = None):
        data = self.tool_get_customer_outstanding(customer_id=customer_id, customer_name=customer_name)
        from masters.models import Customer

        cust = Customer.objects.filter(company=self.company, id=data["customer_id"]).first()
        text = (
            f"Dear {data['customer_name']},\n\n"
            f"This is a friendly reminder that your outstanding balance with us is "
            f"₹{data['outstanding']}. Please arrange payment at your earliest convenience.\n\n"
            f"Thank you,\n{self.company.name}"
        )
        return {
            "draft_text": text,
            "proposed_action": {
                "type": "send_reminder",
                "customer_id": data["customer_id"],
                "customer_name": data["customer_name"],
                "email": (cust.email if cust else "") or "",
                "phone": (cust.phone if cust else "") or "",
                "text": text,
            },
            "citation": {"path": "/sales/customers", "label": "Customers"},
        }


ASSISTANT_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "additionalProperties": False},
        },
    }
    for name, desc, props in [
        ("get_daily_summary", "Daily business KPIs and narrative", {}),
        ("get_health_score", "Business health score and factors", {}),
        ("get_cashflow_forecast", "Cashflow forecast", {"horizon": {"type": "integer"}}),
        ("get_sales_totals", "Sales totals for N days", {"days": {"type": "integer"}}),
        ("get_receivables_aging", "AR aging buckets", {}),
        ("get_payables_aging", "AP aging buckets", {}),
        ("list_business_alerts", "Open business alerts", {}),
        ("list_growth_hints", "Growth and profit-leak hints", {}),
        (
            "get_customer_outstanding",
            "Customer outstanding balance",
            {"customer_id": {"type": "integer"}, "customer_name": {"type": "string"}},
        ),
        (
            "draft_payment_reminder",
            "Draft a payment reminder for confirm-to-send",
            {"customer_id": {"type": "integer"}, "customer_name": {"type": "string"}},
        ),
        ("search_documents", "Search parties and documents", {"q": {"type": "string"}}),
    ]
]


TOOL_ROUTES = [
    ("summary", "get_daily_summary"),
    ("health", "get_health_score"),
    ("cashflow", "get_cashflow_forecast"),
    ("forecast", "get_cashflow_forecast"),
    ("aging", "get_receivables_aging"),
    ("receivable", "get_receivables_aging"),
    ("payable", "get_payables_aging"),
    ("alert", "list_business_alerts"),
    ("hint", "list_growth_hints"),
    ("growth", "list_growth_hints"),
    ("leak", "list_growth_hints"),
    ("sales", "get_sales_totals"),
    ("sold", "get_sales_totals"),
    ("outstanding", "get_customer_outstanding"),
    ("owe", "get_customer_outstanding"),
    ("reminder", "draft_payment_reminder"),
    ("search", "search_documents"),
]


def _pick_tools(message: str) -> list[str]:
    msg = message.lower()
    picked = []
    for needle, tool in TOOL_ROUTES:
        if needle in msg and tool not in picked:
            picked.append(tool)
    if not picked:
        picked = ["get_daily_summary", "list_business_alerts"]
    return picked[:4]


def _run_rules_fallback(company, content: str) -> tuple[str, list, dict | None, str]:
    executor = ToolExecutor(company)
    tools = _pick_tools(content)
    chunks = []
    citations = []
    proposed = None
    name_match = re.search(r"(?:to|for)\s+([A-Za-z][A-Za-z0-9 .&'-]{1,60})", content or "", re.I)
    customer_name = name_match.group(1).strip() if name_match else None
    for tool in tools:
        args: dict[str, Any] = {}
        if tool in ("get_customer_outstanding", "draft_payment_reminder") and customer_name:
            args["customer_name"] = customer_name
        if tool == "get_sales_totals" and "yesterday" in (content or "").lower():
            args["days"] = 1
        try:
            result = executor.run(tool, args)
        except BusinessRuleError as exc:
            chunks.append(f"{tool}: {exc}")
            continue
        cite = result.pop("citation", None)
        if cite:
            citations.append(cite)
        if result.get("proposed_action"):
            proposed = result["proposed_action"]
        chunks.append(f"**{tool}**: {json.dumps(result, default=str)[:1200]}")
    reply = (
        "Here is what your BizBoard documents show (tool-grounded — not tax advice):\n\n"
        + "\n\n".join(chunks)
    )
    if proposed:
        reply += "\n\nA reminder draft is ready — confirm to send (nothing was sent yet)."
    return reply, citations, proposed, "rules+tools"


def _run_llm_tools(company, content: str) -> tuple[str, list, dict | None, str, int, int]:
    from core.services.llm import chat_with_tools

    system = (
        "You are BizBoard Insights assistant. Answer only from tool results. "
        "Never invent tax rates, GSTR filing advice, or cross-company data. "
        "Be concise. Cite which tool you used. "
        "All monetary amounts are in Indian Rupees — always format them with the ₹ symbol, never $ or USD."
    )
    first = chat_with_tools(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        tools=ASSISTANT_TOOL_SCHEMAS,
    )
    tokens_in = int((first.get("usage") or {}).get("tokens_in") or 0)
    tokens_out = int((first.get("usage") or {}).get("tokens_out") or 0)
    executor = ToolExecutor(company)
    citations = []
    proposed = None
    tool_notes = []
    # BB-000309: raise per-tool cap; share a total char budget across tool notes.
    _PER_TOOL_CHARS = 4000
    _TOTAL_TOOL_CHARS = 12_000
    remaining_budget = _TOTAL_TOOL_CHARS
    for tc in first.get("tool_calls") or []:
        name = tc.get("name") or ""
        args = tc.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        args.pop("company_id", None)
        args.pop("company", None)
        try:
            result = executor.run(name, args)
        except BusinessRuleError as exc:
            tool_notes.append(f"{name}: {exc}")
            continue
        cite = result.pop("citation", None)
        if cite:
            citations.append(cite)
        if result.get("proposed_action"):
            proposed = result["proposed_action"]
        raw_json = json.dumps(result, default=str)
        limit = min(_PER_TOOL_CHARS, max(0, remaining_budget))
        truncated = len(raw_json) > limit
        snippet = raw_json[:limit]
        note = f"{name}: {snippet}"
        if truncated:
            note += (
                f"\n[TRUNCATED: tool result cut to {limit} chars — do not invent missing fields]"
            )
        remaining_budget = max(0, remaining_budget - len(note))
        tool_notes.append(note)

    truncation_warning = any("[TRUNCATED:" in n for n in tool_notes)
    if tool_notes:
        second = chat_with_tools(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
                {
                    "role": "assistant",
                    "content": "Tool results:\n" + "\n".join(tool_notes),
                },
                {
                    "role": "user",
                    "content": (
                        "Summarize for the founder using only these tool results."
                        + (
                            " Some tool results were truncated — say so if data may be incomplete."
                            if truncation_warning
                            else ""
                        )
                    ),
                },
            ],
            tools=[],
        )
        tokens_in += int((second.get("usage") or {}).get("tokens_in") or 0)
        tokens_out += int((second.get("usage") or {}).get("tokens_out") or 0)
        reply = second.get("content") or "\n".join(tool_notes)
        if truncation_warning and "[truncated]" not in reply.lower():
            reply += "\n\nNote: some tool data was truncated for length."
    else:
        reply = first.get("content") or "I could not find relevant tools for that question."
    if proposed:
        reply += "\n\nA reminder draft is ready — confirm to send (nothing was sent yet)."
    model = first.get("model") or "llm+tools"
    return reply, citations, proposed, model, tokens_in, tokens_out


def _scrub_tax_output(text: str) -> str:
    """Remove tax-advice phrases; escalate to full refusal if tax intent remains."""
    cleaned = TAX_OUTPUT_STRIP.sub("", text or "").strip()
    if TAX_PATTERNS.search(cleaned):
        return TAX_REFUSAL
    return cleaned or TAX_REFUSAL


def run_assistant_turn(company, user, thread: AssistantThread, content: str) -> AssistantMessage:
    if not company.ai_features_enabled:
        raise BusinessRuleError("AI features are disabled for this company.")
    assert_within_budget(company)

    AssistantMessage.objects.create(
        thread=thread,
        role=AssistantMessage.Role.USER,
        content=content,
    )

    citations: list = []
    proposed = None
    model_name = "rules+tools"
    tokens_in = max(1, len(content) // 4)
    tokens_out = 1

    if _looks_like_tax_question(content or ""):
        reply = TAX_REFUSAL
        citations = [{"path": "/reports/gst-health", "label": "GST Health"}]
    else:
        used_llm = False
        try:
            from core.services.llm import llm_api_key_configured

            if llm_api_key_configured():
                reply, citations, proposed, model_name, tokens_in, tokens_out = _run_llm_tools(
                    company, content,
                )
                used_llm = True
        except Exception:
            used_llm = False
        if not used_llm:
            reply, citations, proposed, model_name = _run_rules_fallback(company, content)
            tokens_out = max(1, len(reply) // 4)
        # BB-000409 / BB-000488: scrub model/rules output that still emits tax advice.
        if TAX_PATTERNS.search(reply or ""):
            reply = TAX_REFUSAL
            proposed = None
            citations = [{"path": "/reports/gst-health", "label": "GST Health"}]
        else:
            scrubbed = _scrub_tax_output(reply or "")
            if scrubbed == TAX_REFUSAL:
                reply = TAX_REFUSAL
                proposed = None
                citations = [{"path": "/reports/gst-health", "label": "GST Health"}]
            else:
                reply = scrubbed

    record_usage(
        company,
        feature=AiUsageLedger.Feature.ASSISTANT,
        tokens_in=max(1, tokens_in),
        tokens_out=max(1, tokens_out),
        model_name=model_name,
    )

    return AssistantMessage.objects.create(
        thread=thread,
        role=AssistantMessage.Role.ASSISTANT,
        content=reply,
        citations=citations,
        proposed_action=proposed,
    )


def confirm_proposed_action(company, user, message_id: int) -> dict:
    """Execute a confirmed assistant proposal from a stored message only."""
    try:
        msg = AssistantMessage.objects.select_related("thread").get(
            pk=message_id,
            thread__company=company,
            role=AssistantMessage.Role.ASSISTANT,
        )
    except AssistantMessage.DoesNotExist as exc:
        raise BusinessRuleError("Assistant message not found.") from exc

    proposed_action = msg.proposed_action
    if not isinstance(proposed_action, dict) or not proposed_action:
        raise BusinessRuleError("No pending proposed action on this message.")

    action_type = proposed_action.get("type")
    if action_type in MONEY_MOVING_ACTION_TYPES:
        raise BusinessRuleError(
            f"Action type {action_type} moves money and cannot be confirmed via assistant; "
            "use the normal document/payment flow with re-auth."
        )
    if action_type not in CONFIRMABLE_ACTION_TYPES:
        raise BusinessRuleError(f"Unsupported action type: {action_type}")

    # Safe UX / draft proposals — clear the proposal; no side effects beyond guidance.
    if action_type in ("NAVIGATE", "SHOW_REPORT"):
        msg.proposed_action = None
        msg.save(update_fields=["proposed_action"])
        return {
            "sent": False,
            "type": action_type,
            "path": proposed_action.get("path") or "",
            "label": proposed_action.get("label") or "",
        }
    if action_type == "CREATE_DRAFT_INVOICE":
        # Draft-only: confirm returns payload for the UI to open create-invoice;
        # never completes or posts money.
        msg.proposed_action = None
        msg.save(update_fields=["proposed_action"])
        return {
            "sent": False,
            "type": action_type,
            "draft": True,
            "payload": {
                k: proposed_action.get(k)
                for k in ("customer_id", "items", "notes")
                if k in proposed_action
            },
        }

    text = (proposed_action.get("text") or "").strip()
    if not text:
        raise BusinessRuleError("Reminder text required.")

    if action_type == "copy_reminder":
        msg.proposed_action = None
        msg.save(update_fields=["proposed_action"])
        return {"sent": False, "copied": True, "text": text}

    from core.models import Notification
    from core.services.notifications import NotificationService
    from masters.models import Customer

    customer_id = proposed_action.get("customer_id")
    cust = None
    if customer_id:
        cust = Customer.objects.filter(company=company, id=customer_id).first()
        if not cust:
            raise BusinessRuleError("Customer not found in this company.")
    # Use stored proposal + company-scoped customer only — never client overrides.
    email = ((cust.email if cust else "") or proposed_action.get("email") or "").strip()
    phone = ((cust.phone if cust else "") or proposed_action.get("phone") or "").strip()

    if email:
        n = NotificationService.send(
            company=company,
            channel=Notification.Channel.EMAIL,
            recipient=email,
            subject=f"Payment reminder from {company.name}",
            body=text,
            user=user,
        )
        msg.proposed_action = None
        msg.save(update_fields=["proposed_action"])
        return {
            "sent": True,
            "channel": "EMAIL",
            "notification_id": n.id,
            "recipient": email,
        }
    if phone:
        n = NotificationService.send(
            company=company,
            channel=Notification.Channel.WHATSAPP,
            recipient=phone,
            subject="",
            body=text,
            user=user,
        )
        msg.proposed_action = None
        msg.save(update_fields=["proposed_action"])
        return {
            "sent": False,
            "requires_user_share": True,
            "channel": "WHATSAPP",
            "notification_id": n.id,
            "share_link": n.share_link,
        }
    raise BusinessRuleError("Customer has no email or phone to send a reminder.")


def dismiss_proposed_action(company, message_id: int) -> dict:
    try:
        msg = AssistantMessage.objects.select_related("thread").get(
            pk=message_id,
            thread__company=company,
            role=AssistantMessage.Role.ASSISTANT,
        )
    except AssistantMessage.DoesNotExist as exc:
        raise BusinessRuleError("Assistant message not found.") from exc
    if not msg.proposed_action:
        return {"dismissed": True}
    msg.proposed_action = None
    msg.save(update_fields=["proposed_action"])
    return {"dismissed": True}
