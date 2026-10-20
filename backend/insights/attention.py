"""B-05 Business Attention Center — one ranked feed, frozen AttentionRow contract.

Downstream waves (M/Q/R) must emit this shape only. No LLM.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .alerts import (
    build_business_alerts,
    build_leakage_detectors,
    detector_status,
    report_detector_failure,
    report_detector_truncated,
)
from .models import AttentionRowState
from .services import build_growth_hints

# B9-012: the raw feed (_overdue_customer_rows especially -- a per-customer
# outstanding/aging/avg-delay computation, up to 30 customers) is the
# expensive, user-independent part of this endpoint. Cache it per
# (company, as_of) briefly; per-user dismiss/snooze state and the
# capability filter below still run fresh on every request.
logger = logging.getLogger(__name__)

_ATTENTION_RAW_TTL = 60

ATTENTION_ROW_KEYS = (
    "code",
    "severity",
    "title",
    "money_impact_paise",
    "currency",
    "reason",
    "action_label",
    "action_href",
    "source_ticket",
    "entity_ref",
    "dedupe_key",
    "first_seen",
    "snooze_until",
    # DAN-04: the server decides what may be done to a row; the UI reads these flags.
    "dismissible",
    "snoozable",
    "assignable",
    "requires_reason",
    # DAN-09 / DAN-12
    "amount_basis",
    "age_days",
    "is_new",
    "state",
    "state_by",
    "state_at",
    "state_reason",
    # DAN-11: structured values behind title/reason so the client can translate them.
    "params",
)

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

# Codes a cashier / sales staff must not see (margin / leakage / GST money).
FINANCIAL_CODES = frozenset({
    "AR_OVERDUE_CRITICAL",
    "AR_OVERDUE_WARN",
    "AR_RESIDUAL_AFTER_RETURN",
    "AP_DUE_7D",
    "CREDIT_LIMIT_NEAR",
    "CUSTOMER_CONCENTRATION",
    "MARGIN_DROP_SKU",
    "MARGIN_COMPRESSION",
    "SALE_BELOW_COST",
    "DISCOUNT_OVER_THRESHOLD",
    "DISCOUNT_STACKED",
    "PURCHASE_PRICE_JUMP",
    "PURCHASE_PRICE_CREEP",
    "CASH_TIGHT_14D",
    "ITC_AT_RISK",
    "GSTR2B_UNMATCHED",
    "GST_HEALTH_CRITICAL_OPEN",
    "GST_GUARDRAIL",
    "GST_RATE_EXPOSURE",
    "DUPLICATE_PAYMENT",
    "OVERDUE_CONCENTRATION",
    "DISCOUNT_FREQUENCY",
})
GST_CODES = frozenset({
    "ITC_AT_RISK",
    "GSTR2B_UNMATCHED",
    "GST_HEALTH_CRITICAL_OPEN",
    "GST_GUARDRAIL",
    "GST_RATE_EXPOSURE",
    "EINVOICE_FAILED",
    "EINVOICE_PENDING",
    "IRN_FAILED",
})
STOCK_CODES = frozenset({
    "LOW_STOCK_FAST_MOVER",
    "DEAD_STOCK",
    "EXPIRING_STOCK",
    "ABNORMAL_STOCK_ADJUSTMENT",
})
HINT_SKIP_IF_ALERT = frozenset({
    "CUSTOMER_CONCENTRATION",
    "MARGIN_DROP_SKU",
    "OVERDUE_CONCENTRATION",
    "DEAD_STOCK",
})

# DAN-04. Rows that must be fixed, not hidden: a tax, e-invoice or books problem does not go
# away because someone dismissed it. They can still be snoozed and assigned (an owner has to be
# able to hand a GST fix to the accountant). Enforced in dismiss_attention_row, not only in the UI.
NON_DISMISSIBLE = frozenset({
    "GST_GUARDRAIL",
    "GST_RATE_EXPOSURE",
    "ITC_AT_RISK",
    "GSTR2B_UNMATCHED",
    "GST_HEALTH_CRITICAL_OPEN",
    "EINVOICE_FAILED",
    "EINVOICE_PENDING",
    "IRN_FAILED",
    "PAID_PENDING_BOOKS",
    "FEED_DEGRADED",
})
# Every code a detector can emit (docs/ATTENTION_DEDUPE_KEYS.md). A key for any other code is refused,
# so a mistyped or made-up key cannot create state. tests/test_dan_phase_d_attention.py keeps this in
# step with what the detectors emit.
KNOWN_CODES = frozenset({
    "ABNORMAL_STOCK_ADJUSTMENT", "AP_DUE_7D", "AR_COLLECTION_RISK", "AR_CUSTOMER", "AR_OVERDUE_CRITICAL",
    "AR_OVERDUE_WARN", "AR_RESIDUAL_AFTER_RETURN", "CASH_TIGHT_14D", "CHURN_RISK", "CONTRACT_RENEWAL",
    "CREDIT_LIMIT_NEAR", "CROSS_SELL", "CUSTOMER_CONCENTRATION", "DEAD_STOCK", "DISCOUNT_FREQUENCY",
    "DISCOUNT_OVER_THRESHOLD", "DISCOUNT_STACKED", "DUPLICATE_PAYMENT", "EXPIRING_STOCK", "FEED_DEGRADED",
    "GST_GUARDRAIL", "GST_HEALTH_CRITICAL_OPEN", "GST_RATE_EXPOSURE", "IRN_FAILED", "ITC_AT_RISK",
    "JOB_READY_TO_INVOICE", "LOW_STOCK_FAST_MOVER", "MARGIN_COMPRESSION", "MARGIN_DROP_SKU",
    "MILESTONE_OVERDUE", "NO_SALES_TODAY", "OVERDUE_CONCENTRATION", "PAID_PENDING_BOOKS",
    "PREDICTED_LATE_PAYMENT", "PROMISE_TO_PAY_DUE", "PURCHASE_PRICE_CREEP", "PURCHASE_PRICE_JUMP",
    "QUOTATION_EXPIRED", "QUOTATION_EXPIRING", "REPEAT_ORDER_DUE", "SALE_BELOW_COST", "TICKET_SLA_BREACH",
    "VOID_RATE_HIGH", "WALK_IN_UNALLOCATED_RECEIPT",
    # classified above but not emitted by any detector today
    "EINVOICE_FAILED", "EINVOICE_PENDING", "GSTR2B_UNMATCHED",
})
NON_SNOOZABLE = frozenset({"FEED_DEGRADED"})
NON_ASSIGNABLE = frozenset({"FEED_DEGRADED"})
# Setting these aside always needs a reason, whatever their severity today.
REASON_REQUIRED_CODES = frozenset({"DUPLICATE_PAYMENT"})
MIN_REASON_LENGTH = 3

_TWOPLACES = Decimal("0.01")


def rupees_to_paise(amount) -> int:
    value = Decimal(str(amount or 0)).quantize(_TWOPLACES, rounding=ROUND_HALF_UP)
    return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


# DAN-07: a Fix button must never lead back to the dashboard. When a detector gives no link,
# the row falls back to the page that lists the problem's kind, not to "/".
FALLBACK_HREF_BY_KIND = {
    "receivable": "/payments/collections",
    "payable": "/reports/supplier-ledger",
    "stock": "/inventory/stock",
    "gst": "/reports/gst-health",
    "margin": "/reports/sales",
    "discount": "/reports/sales-discounts",
    "purchase": "/purchases/history",
    "cash": "/insights/cashflow",
}


def fallback_href(code: str) -> str:
    from .event_schema import EVENT_SOURCES

    kind = (EVENT_SOURCES.get(code) or {}).get("kind")
    return FALLBACK_HREF_BY_KIND.get(kind, "/attention")


def _clip_title(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= 80:
        return text
    return text[:77] + "..."


def _iso(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.isoformat()


def _row(
    *,
    code: str,
    severity: str,
    title: str,
    money_impact_paise: int,
    reason: str,
    action_label: str,
    action_href: str,
    source_ticket: str,
    entity_type: str,
    entity_id: int,
    dedupe_key: str | None = None,
    params: dict | None = None,
) -> dict[str, Any]:
    key = dedupe_key or f"{code}:{entity_type}:{entity_id}"
    return {
        "code": code,
        "severity": severity if severity in SEVERITY_RANK else "info",
        "title": _clip_title(title),
        "money_impact_paise": int(money_impact_paise or 0),
        "currency": "INR",
        "reason": (reason or "").strip(),
        "action_label": action_label or "Open",
        "action_href": action_href if action_href and action_href != "/" else fallback_href(code),
        "source_ticket": source_ticket,
        "entity_ref": {"type": entity_type, "id": int(entity_id)},
        "dedupe_key": key,
        "first_seen": None,
        "snooze_until": None,
        "params": params or {},
    }


def row_policy(code: str, severity: str) -> dict[str, bool]:
    return {
        "dismissible": code not in NON_DISMISSIBLE,
        "snoozable": code not in NON_SNOOZABLE,
        "assignable": code not in NON_ASSIGNABLE,
        "requires_reason": code in REASON_REQUIRED_CODES or severity == "critical",
    }


# What the amount on a row measures. Amounts of different kinds are not comparable, so the UI says which.
AMOUNT_BASIS = {
    "IRN_FAILED": "invoice_total",
    "GST_RATE_EXPOSURE": "tax_delta",
    "ITC_AT_RISK": "credit_at_risk",
    "PAID_PENDING_BOOKS": "received_not_posted",
    "PROMISE_TO_PAY_DUE": "promised",
    "AR_RESIDUAL_AFTER_RETURN": "overdue",
    "AR_COLLECTION_RISK": "overdue",
    "AR_CUSTOMER": "overdue",
    "AR_OVERDUE_CRITICAL": "overdue",
    "AR_OVERDUE_WARN": "overdue",
    "AP_DUE_7D": "payable_due",
}


def _contract(row: dict) -> dict:
    meta = {
        "amount_basis": "none" if not row.get("money_impact_paise") else AMOUNT_BASIS.get(row["code"], "amount"),
        "age_days": 0,
        "is_new": False,
        "state": "open",
        "state_by": None,
        "state_at": None,
        "state_reason": "",
        "params": {},
    }
    row = {**meta, **row, **row_policy(row["code"], row["severity"])}
    return {k: row[k] for k in ATTENTION_ROW_KEYS}


def _can_see(company_user, code: str) -> bool:
    """Does this person handle this kind of item?

    The feed endpoint needs financial reports, so for the feed this is almost always true. It is
    kept for the second use: an item may be assigned to an operational team member (sales,
    inventory, payments) who cannot open the feed, and only to someone who handles that kind of item.
    """
    if company_user is None:
        return False
    if company_user.role == "OWNER":
        return True
    if code in FINANCIAL_CODES or code in GST_CODES:
        return bool(company_user.can_view_financial_reports)
    if code in STOCK_CODES:
        return bool(
            company_user.can_manage_inventory
            or company_user.can_view_financial_reports
            or company_user.can_create_purchases
        )
    if code in {"PAID_PENDING_BOOKS", "DUPLICATE_PAYMENT", "WALK_IN_UNALLOCATED_RECEIPT", "VOID_RATE_HIGH"}:
        return bool(company_user.can_create_payments or company_user.can_view_financial_reports)
    if code in {
        "TICKET_SLA_BREACH", "CONTRACT_RENEWAL", "MILESTONE_OVERDUE", "JOB_READY_TO_INVOICE",
        "QUOTATION_EXPIRED", "QUOTATION_EXPIRING",
    }:
        return bool(company_user.can_create_sales or company_user.can_view_financial_reports)
    if code in {
        "NO_SALES_TODAY",
        "AR_OVERDUE_CUSTOMER",
        "CHURN_RISK",
        "REPEAT_ORDER_DUE",
        "CROSS_SELL",
        "PREDICTED_LATE_PAYMENT",
        "PROMISE_TO_PAY_DUE",
        "AR_COLLECTION_RISK",
        "AR_CUSTOMER",
    }:
        return bool(
            company_user.can_create_sales
            or company_user.can_create_payments
            or company_user.can_view_financial_reports
        )
    return bool(company_user.can_view_financial_reports)


def _paise_from_legacy_alert(row: dict) -> int:
    payload = row.get("payload") or {}
    code = row.get("code") or ""
    aging = payload.get("aging") or {}
    if code == "AR_OVERDUE_CRITICAL":
        return rupees_to_paise(aging.get("days_90_plus") or 0)
    if code == "AR_OVERDUE_WARN":
        return rupees_to_paise(aging.get("days_31_60") or 0)
    if code == "AP_DUE_7D":
        return rupees_to_paise(payload.get("ap_due_7d") or 0)
    return 0


def _map_legacy_alerts(company, as_of: date) -> list[dict]:
    out = []
    for raw in build_business_alerts(company, as_of=as_of):
        code = raw.get("code") or "ALERT"
        doc_type = raw.get("document_type") or "company"
        doc_id = raw.get("document_id") or company.id
        href = raw.get("cta_path") or fallback_href(code)
        action_label = "Fix"
        payload = raw.get("payload") or {}
        if code == "LOW_STOCK_FAST_MOVER" and payload.get("suggested_qty"):
            action_label = "Transfer" if payload.get("transfer_from_warehouse_id") else "Purchase"
        out.append(_row(
            code=code,
            severity=raw.get("severity") or "info",
            title=raw.get("message") or code,
            money_impact_paise=_paise_from_legacy_alert(raw),
            reason=raw.get("message") or code,
            action_label=action_label,
            action_href=href,
            source_ticket="B-05",
            entity_type=doc_type,
            entity_id=int(doc_id),
            dedupe_key=f"{code}:{raw.get('subject_key') or f'{doc_type}:{doc_id}'}",
            params=raw.get("params"),
        ))
    return out


def _map_hints(company, as_of: date, seen_codes: set[str]) -> list[dict]:
    out = []
    for hint in build_growth_hints(company, as_of=as_of):
        code = hint.get("code") or "HINT"
        if code in HINT_SKIP_IF_ALERT:
            continue
        if code in seen_codes:
            continue
        paise = rupees_to_paise(hint.get("impact_estimate") or 0)
        out.append(_row(
            code=code,
            severity=hint.get("severity") or "info",
            title=hint.get("title") or code,
            money_impact_paise=paise,
            reason=hint.get("message") or (hint.get("title") or code),
            action_label="Open",
            action_href=hint.get("cta_path") or fallback_href(code),
            source_ticket="B-05",
            entity_type="company",
            entity_id=company.id,
            dedupe_key=f"{code}:hint:{company.id}",
            params=hint.get("params"),
        ))
    return out


def _itc_and_gst_rows(company, as_of: date) -> list[dict]:
    """B-03: credit-at-risk from the IMS board (unresolved / expiring ITC)."""
    from reporting.gst_health import build_gst_health
    from reporting.ims import credit_at_risk
    from reporting.models import Gstr2bIngest

    rows = []
    period = f"{as_of.year:04d}-{as_of.month:02d}"
    if Gstr2bIngest.objects.filter(company=company, period=period).exists():
        summary = credit_at_risk(company, period, as_of=as_of)
        paise = int(summary.get("itc_at_risk_paise") or 0)
        if paise > 0 or int(summary.get("expiring_count") or 0):
            exp = summary.get("expiring_itc") or "0"
            rows.append(_row(
                code="ITC_AT_RISK",
                severity="critical",
                title="ITC at risk this month",
                money_impact_paise=paise,
                reason=(
                    f"Unresolved IMS credit ₹{summary.get('itc_at_risk')}; "
                    f"₹{exp} expiring within 30 days of the Section 16(4) window."
                ),
                action_label="Open IMS board",
                action_href="/reports/gstr2b",
                source_ticket="B-03",
                entity_type="gst_period",
                entity_id=int(as_of.strftime("%Y%m")),
                dedupe_key=f"ITC_AT_RISK:{period}",
                params={"amount": str(summary.get("itc_at_risk")), "expiring": str(exp)},
            ))
    try:
        gst = build_gst_health(company)
    except Exception:
        report_detector_failure("gst_health")
        return rows
    # Filter to critical first, then cap — capping the raw list before
    # filtering can drop a real critical alert (including from a later
    # invoice in the same run) whenever earlier invoices produce 25+ raw
    # alerts of any severity, while the summary count still shows the truth.
    critical = [alert for alert in (gst.get("alerts") or []) if alert.get("severity") == "critical"]
    if len(critical) > 25:
        report_detector_truncated("GST_GUARDRAIL")
    for alert in critical[:25]:
        doc_type = alert.get("document_type") or "company"
        doc_id = alert.get("document_id") or company.id
        href = "/reports/gst-health"
        if doc_type == "sales_invoice":
            href = f"/sales/history/{doc_id}"
        elif doc_type == "purchase_invoice":
            href = f"/purchases/history/{doc_id}"
        rows.append(_row(
            code="GST_GUARDRAIL",
            severity="critical",
            title=alert.get("message") or alert.get("code") or "GST issue",
            money_impact_paise=0,
            reason=alert.get("message") or "",
            action_label="Fix",
            action_href=href,
            source_ticket="B-04",
            entity_type=doc_type,
            entity_id=int(doc_id),
            dedupe_key=f"GST_GUARDRAIL:{alert.get('code')}:{doc_type}:{doc_id}",
        ))
    return rows


def _gst_rate_exposure_rows(company, as_of: date) -> list[dict]:
    from reporting.gst_rate_scan import backscan_rate_exposure

    scan = backscan_rate_exposure(company, date_from=date(2025, 9, 22), date_to=as_of)
    count = int(scan.get("count") or 0)
    if count <= 0:
        return []
    paise = rupees_to_paise(scan.get("estimated_exposure") or 0)
    return [_row(
        code="GST_RATE_EXPOSURE",
        severity="warning",
        title="GST rate exposure after GST 2.0",
        money_impact_paise=abs(paise),
        reason=(
            f"{count} completed invoice line(s) billed a rate that is not the table rate "
            f"on the document date. Estimated tax delta ₹{scan.get('estimated_exposure')}."
        ),
        action_label="Review GST rates on these bills",
        action_href="/reports/gst-rate-exposure",
        source_ticket="B-06",
        entity_type="company",
        entity_id=company.id,
        dedupe_key=f"GST_RATE_EXPOSURE:{company.id}",
        params={"count": count, "delta": str(scan.get("estimated_exposure"))},
    )]


def _irn_rows(company) -> list[dict]:
    from sales.models import SalesInvoice

    rows = []
    qs = list(SalesInvoice.objects.filter(
        company=company,
        status=SalesInvoice.Status.COMPLETED,
        einvoice_status=SalesInvoice.EInvoiceStatus.FAILED,
    ).only("id", "number", "grand_total")[:21])
    if len(qs) > 20:
        report_detector_truncated("IRN_FAILED")
    for inv in qs[:20]:
        rows.append(_row(
            code="IRN_FAILED",
            severity="warning",
            title=f"IRN failed on {inv.number or inv.id}",
            money_impact_paise=rupees_to_paise(inv.grand_total),
            reason="E-invoice generation failed — retry or record a manual IRN.",
            action_label="Open invoice",
            action_href=f"/sales/history/{inv.id}",
            source_ticket="B-01",
            entity_type="sales_invoice",
            entity_id=inv.id,
            params={"number": str(inv.number or inv.id)},
        ))
    return rows


def _paid_pending_books_rows(company) -> list[dict]:
    from payments.models import GatewayPayment, GatewayPaymentStatus, PaymentLink, PaymentLinkStatus

    rows = []
    links = list(PaymentLink.objects.filter(
        company=company,
        status=PaymentLinkStatus.PAID,
        paid_receipt__isnull=True,
    ).only("id", "amount")[:21])
    if len(links) > 20:
        report_detector_truncated("PAID_PENDING_BOOKS")
    for link in links[:20]:
        rows.append(_row(
            code="PAID_PENDING_BOOKS",
            severity="critical",
            title="Gateway paid — receipt not posted",
            money_impact_paise=rupees_to_paise(link.amount),
            reason="A payment link is PAID but no customer receipt is linked.",
            action_label="Post receipt",
            action_href="/payments/links",
            source_ticket="W0-03",
            entity_type="payment_link",
            entity_id=link.id,
            params={"variant": "link"},
        ))
    captured = list(
        GatewayPayment.objects.filter(
            company=company,
            status__in=(
                GatewayPaymentStatus.CAPTURED,
                GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
            ),
            receipts__isnull=True,
        )
        .distinct()
        .only("id", "amount", "status")[:21]
    )
    if len(captured) > 20:
        report_detector_truncated("PAID_PENDING_BOOKS")
    for gp in captured[:20]:
        rows.append(_row(
            code="PAID_PENDING_BOOKS",
            severity="critical",
            title="Captured payment with no receipt",
            money_impact_paise=rupees_to_paise(gp.amount),
            reason="Gateway capture has no linked customer receipt.",
            action_label="Post receipt",
            action_href="/payments/links",
            source_ticket="W0-03",
            entity_type="gateway_payment",
            entity_id=gp.id,
            params={"variant": "capture"},
        ))
    return rows


def _overdue_customer_rows(company, as_of: date) -> list[dict]:
    from ledgers.services import LedgerService
    from masters.models import Customer
    from payments.dunning import customer_risk_snapshot
    from sales.models import SalesInvoice

    rows = []
    cutoff = as_of - timedelta(days=1)
    # DAN-15: pick the customers who really owe overdue money in two bulk queries, then build the
    # expensive snapshot only for them. The old code took the first 30 customers with an overdue
    # *date*, paid or not, so paid ones could crowd out a customer who still owed.
    overdue_invoices = list(
        SalesInvoice.objects.filter(
            company=company,
            status=SalesInvoice.Status.COMPLETED,
            due_date__lte=cutoff,
        ).values_list("id", "customer_id")
    )
    outstanding = LedgerService.bulk_sales_invoice_outstanding(
        company, invoice_ids=[invoice_id for invoice_id, _cid in overdue_invoices]
    )
    owed_by_customer: dict[int, Decimal] = {}
    for invoice_id, customer_id in overdue_invoices:
        owed = outstanding.get(invoice_id) or Decimal("0")
        if owed > 0 and customer_id is not None:
            owed_by_customer[customer_id] = owed_by_customer.get(customer_id, Decimal("0")) + owed
    ranked_ids = sorted(owed_by_customer, key=lambda cid: (-owed_by_customer[cid], cid))
    if len(ranked_ids) > 30:
        report_detector_truncated("AR_COLLECTION_RISK")
    cust_ids = ranked_ids[:30]
    customers = Customer.objects.in_bulk(cust_ids) if cust_ids else {}
    for cid in cust_ids:
        cust = customers.get(cid)
        if not cust or cust.company_id != company.id:
            continue
        snap = customer_risk_snapshot(company, cust, as_of=as_of)
        overdue = Decimal(snap["overdue_amount"])
        if overdue <= 0:
            continue
        step = snap["recommended_next_step"].replace("_", " ")
        rows.append(_row(
            code="AR_COLLECTION_RISK",
            severity="critical" if snap["collection_status"] in ("stop_credit", "overdue_severe") else "warning",
            title=f"{cust.name}: {snap['collection_status'].replace('_', ' ')}",
            money_impact_paise=rupees_to_paise(overdue),
            reason=(
                f"{cust.name} overdue ₹{overdue}. "
                f"Next: {step}."
            ),
            action_label=step[:40].title(),
            action_href=f"/reports/customer-ledger?customer={cust.id}",
            source_ticket="A-07",
            entity_type="customer",
            entity_id=cust.id,
            params={
                "customer": cust.name,
                "status": snap["collection_status"],
                "amount": str(overdue),
                "step": snap["recommended_next_step"],
            },
        ))
    return rows


def _residual_return_rows(company) -> list[dict]:
    """P5-T2: a RETURNED invoice that still owes money is residual AR, not 'Paid'."""
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    rows = []
    returned = list(SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.RETURNED)[:41])
    if len(returned) > 40:
        report_detector_truncated("AR_RESIDUAL_AFTER_RETURN")
    returned = returned[:40]
    owed_by_id = LedgerService.bulk_sales_invoice_outstanding(company, invoice_ids=[inv.id for inv in returned])
    for inv in returned:
        outstanding = owed_by_id.get(inv.id) or Decimal("0")
        if outstanding <= 0:
            continue
        number = inv.number or inv.pk
        rows.append(_row(
            code="AR_RESIDUAL_AFTER_RETURN",
            severity="warning",
            title=f"{number}: residual balance after return",
            money_impact_paise=rupees_to_paise(outstanding),
            reason=f"residual balance after return ₹{outstanding} on {number}",
            action_label="Open invoice",
            action_href=f"/sales/history/{inv.id}",
            source_ticket="P5-T2",
            entity_type="sales_invoice",
            entity_id=inv.id,
            params={"number": str(number), "amount": str(outstanding)},
        ))
    return rows


def _promise_to_pay_rows(company, as_of: date) -> list[dict]:
    """Customer promise-to-pay commitments due today (unresolved)."""
    from payments.promise_to_pay import promises_due_today

    rows = []
    due = list(promises_due_today(company, as_of=as_of)[:41])
    if len(due) > 40:
        report_detector_truncated("PROMISE_TO_PAY_DUE")
    for promise in due[:40]:
        customer = promise.customer
        if promise.promised_amount is None:
            amount_note = "amount not recorded"
            impact = Decimal("0")
        else:
            amount_note = f"₹{promise.promised_amount}"
            impact = promise.promised_amount
        rows.append(_row(
            code="PROMISE_TO_PAY_DUE",
            severity="warning",
            title=f"{customer.name} promised to pay {amount_note} today",
            money_impact_paise=rupees_to_paise(impact) if promise.promised_amount is not None else 0,
            reason=(
                "amount not recorded. "
                if promise.promised_amount is None
                else ""
            ) + (
                promise.note.strip() if promise.note.strip()
                else f"{customer.name} committed to pay on {promise.promised_date.isoformat()}."
            ),
            action_label="Open collections",
            action_href="/payments/collections",
            source_ticket="PROMISE_TO_PAY",
            entity_type="customer",
            entity_id=customer.id,
            dedupe_key=f"PROMISE_TO_PAY_DUE:{promise.id}",
            params={
                "variant": ("amount" if promise.promised_amount is not None else "no_amount")
                + ("_note" if promise.note.strip() else ""),
                "titleVariant": "amount" if promise.promised_amount is not None else "no_amount",
                "customer": customer.name,
                "date": promise.promised_date.isoformat(),
                **({"amount": str(promise.promised_amount)} if promise.promised_amount is not None else {}),
                **({"note": promise.note.strip()} if promise.note.strip() else {}),
            },
        ))
    return rows


def _expiry_rows(company) -> list[dict]:
    from inventory.item_stock import expiry_horizon_rows

    rows = []
    try:
        horizon = expiry_horizon_rows(company, days=30)
    except Exception:
        report_detector_failure("expiry")
        return rows
    expired_or_soon = [r for r in horizon if r.get("expired") or int(r.get("days_to_expiry") or 0) <= 30]
    if not expired_or_soon:
        return rows
    # One row per product (worst lot), cap 15.
    seen: set[int] = set()
    for item in expired_or_soon:
        pid = int(item["product"])
        if pid in seen:
            continue
        if len(rows) >= 15:
            report_detector_truncated("EXPIRING_STOCK")
            break
        seen.add(pid)
        days = int(item.get("days_to_expiry") or 0)
        reason = (
            f"{item['product_name']} lot {item.get('batch_no') or ''} "
            f"{'expired' if item.get('expired') else f'expires in {days} days'}."
        )
        rows.append(_row(
            code="EXPIRING_STOCK",
            severity="critical" if item.get("expired") else "warning",
            title=f"Expiring stock — {item['product_name']}",
            money_impact_paise=0,
            reason=reason.strip(),
            action_label="Open expiry board",
            action_href="/inventory/expiry-alerts",
            source_ticket="C-03",
            entity_type="product",
            entity_id=pid,
            dedupe_key=f"EXPIRING_STOCK:{pid}",
            params={
                "variant": "expired" if item.get("expired") else "soon",
                "product": item["product_name"],
                "batch": str(item.get("batch_no") or ""),
                "days": days,
            },
        ))
    return rows


def _merge_and_rank(raw: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for row in raw:
        key = row["dedupe_key"]
        existing = by_key.get(key)
        if existing is None or abs(row["money_impact_paise"]) > abs(existing["money_impact_paise"]):
            by_key[key] = row
    ranked = list(by_key.values())
    ranked.sort(
        key=lambda r: (
            SEVERITY_RANK.get(r["severity"], 9),
            -abs(int(r["money_impact_paise"] or 0)),
            r["dedupe_key"],
        )
    )
    return ranked


# DAN-08. These four describe the same thing from different angles: this customer owes money.
AR_CUSTOMER_SOURCES = frozenset({
    "AR_COLLECTION_RISK",
    "PREDICTED_LATE_PAYMENT",
    "PROMISE_TO_PAY_DUE",
    "CREDIT_LIMIT_NEAR",
})


def _fingerprint(severity: str, codes) -> str:
    return f"{SEVERITY_RANK.get(severity, 9)}|{','.join(sorted(set(codes)))}"


def _escalated(old: str, new: str) -> bool:
    """A set-aside row comes back when a new signal appears or its severity rises."""
    if not old or not new:
        return False
    old_rank, _, old_codes = old.partition("|")
    new_rank, _, new_codes = new.partition("|")
    try:
        higher = int(new_rank) < int(old_rank)
    except ValueError:
        higher = False
    return higher or bool(set(new_codes.split(",")) - set(old_codes.split(",")))


def _merge_customer_receivables(rows: list[dict]) -> list[dict]:
    """One row per customer for the signals in AR_CUSTOMER_SOURCES (DAN-08)."""
    groups: dict[int, list[dict]] = {}
    rest: list[dict] = []
    for row in rows:
        ref = row.get("entity_ref") or {}
        if row["code"] in AR_CUSTOMER_SOURCES and ref.get("type") == "customer":
            groups.setdefault(int(ref["id"]), []).append(row)
        else:
            rest.append(row)
    if not groups:
        return rows

    from masters.models import Customer

    names = dict(Customer.objects.filter(pk__in=list(groups)).values_list("pk", "name"))
    merged = []
    for customer_id, members in groups.items():
        members.sort(key=lambda r: (SEVERITY_RANK.get(r["severity"], 9), -abs(int(r["money_impact_paise"] or 0))))
        top = members[0]
        severity = top["severity"]
        name = names.get(customer_id) or "Customer"
        if len(members) == 1:
            title = top["title"]
        else:
            title = f"{name}: {len(members)} receivable issues"
        reasons = []
        for member in members:
            text = (member["reason"] or "").strip()
            if text and text not in reasons:
                reasons.append(text)
        row = _row(
            code="AR_CUSTOMER",
            severity=severity,
            title=title,
            money_impact_paise=max(abs(int(m["money_impact_paise"] or 0)) for m in members),
            reason=" ".join(reasons)[:600],
            action_label=top["action_label"],
            action_href=top["action_href"],
            source_ticket="DAN-08",
            entity_type="customer",
            entity_id=customer_id,
            dedupe_key=f"AR_CUSTOMER:{customer_id}",
            params={
                "customer": name,
                "count": len(members),
                # Each signal keeps its own values so the client can translate the combined text.
                "signals": [
                    {"code": m["code"], "params": m.get("params") or {}, "title": m["title"], "reason": m["reason"]}
                    for m in members
                ],
            },
        )
        row["signal_fingerprint"] = _fingerprint(severity, (m["code"] for m in members))
        merged.append(row)
    return rest + merged


# DAN-05. Which codes each detector owns. A failed or capped detector cannot tell "condition gone"
# from "could not look", so only ITS codes keep their state this round; others carry on normally.
_LEGACY_ALERT_CODES = {
    "ar_overdue": {"AR_OVERDUE_CRITICAL", "AR_OVERDUE_WARN"},
    "ap_due": {"AP_DUE_7D"},
    "low_stock": {"LOW_STOCK_FAST_MOVER"},
    "no_sales": {"NO_SALES_TODAY"},
    "customer_concentration": {"CUSTOMER_CONCENTRATION"},
    "credit_limit": {"CREDIT_LIMIT_NEAR", "AR_CUSTOMER"},
    "margin_drop": {"MARGIN_DROP_SKU"},
    "cash_tight": {"CASH_TIGHT_14D"},
    "gst_health": {"GST_HEALTH_CRITICAL_OPEN"},
    "ticket_sla": {"TICKET_SLA_BREACH"},
    "contract_renewal": {"CONTRACT_RENEWAL"},
    "milestone_overdue": {"MILESTONE_OVERDUE"},
    "jobs_ready": {"JOB_READY_TO_INVOICE"},
    "quotation_expiry": {"QUOTATION_EXPIRED", "QUOTATION_EXPIRING"},
}
DETECTOR_CODES: dict[str, set[str]] = {
    **{f"alerts.{name}": codes for name, codes in _LEGACY_ALERT_CODES.items()},
    "alerts": set().union(*_LEGACY_ALERT_CODES.values()),
    "growth_hints": {
        "PURCHASE_PRICE_CREEP", "DISCOUNT_FREQUENCY", "OVERDUE_CONCENTRATION", "DEAD_STOCK",
        "CUSTOMER_CONCENTRATION", "MARGIN_DROP_SKU",
    },
    "leakage": {
        "SALE_BELOW_COST", "DISCOUNT_STACKED", "DISCOUNT_OVER_THRESHOLD", "MARGIN_COMPRESSION",
        "PURCHASE_PRICE_JUMP", "ABNORMAL_STOCK_ADJUSTMENT", "DUPLICATE_PAYMENT", "VOID_RATE_HIGH",
        "WALK_IN_UNALLOCATED_RECEIPT", "DEAD_STOCK",
    },
    "gst_itc": {"ITC_AT_RISK", "GST_GUARDRAIL"},
    "gst_health": {"ITC_AT_RISK", "GST_GUARDRAIL"},
    "gst_rate_exposure": {"GST_RATE_EXPOSURE"},
    "irn": {"IRN_FAILED"},
    "paid_pending_books": {"PAID_PENDING_BOOKS"},
    "overdue_customers": {"AR_COLLECTION_RISK", "AR_CUSTOMER"},
    "expiry": {"EXPIRING_STOCK"},
    "promise_to_pay": {"PROMISE_TO_PAY_DUE", "AR_CUSTOMER"},
    "predicted_dunning": {"PREDICTED_LATE_PAYMENT", "AR_CUSTOMER"},
    "customer_actions": {"CHURN_RISK", "REPEAT_ORDER_DUE", "CROSS_SELL"},
    "residual_returns": {"AR_RESIDUAL_AFTER_RETURN"},
}


def _paused_codes(status: dict):
    """Codes whose state must be left alone this round, or None when we cannot say which."""
    held: set[str] = set(status.get("truncated") or [])
    for name in status.get("failed") or []:
        owned = DETECTOR_CODES.get(name)
        if owned is None:
            return None
        held |= owned
    return held


_FIRST_SEEN_BUCKET_MINUTES = 5


def _first_seen_fallback(now):
    """A row with no stored state yet: a value that does not advance on every refresh.

    The sweep (sweep_attention_state) stores the real first_seen within one bucket.
    """
    minute = now.minute - now.minute % _FIRST_SEEN_BUCKET_MINUTES
    return now.replace(minute=minute, second=0, microsecond=0)


def _apply_state(company, ranked: list[dict], now=None) -> tuple[list[dict], dict]:
    """Hide dismissed/snoozed rows. Read-only: a GET must not write (DAN-06)."""
    now = now or timezone.now()
    keys = [r["dedupe_key"] for r in ranked]
    existing = {
        s.dedupe_key: s
        for s in AttentionRowState.objects.filter(company=company, dedupe_key__in=keys)
    }
    fallback = _iso(_first_seen_fallback(now))
    visible = []
    for row in ranked:
        state = existing.get(row["dedupe_key"])
        if state is None:
            row["first_seen"] = fallback
            row["snooze_until"] = None
            visible.append(row)
            continue
        set_aside = state.dismissed or bool(state.snooze_until and state.snooze_until > now)
        if set_aside and not _escalated(state.signal_fingerprint, row.get("signal_fingerprint", "")):
            continue
        row["first_seen"] = _iso(state.first_seen)
        row["snooze_until"] = None
        visible.append(row)
    return visible, existing


def _guard(name: str, status: dict, fn, *args):
    """Run one detector; a crash becomes a visible failure, never a silent empty list."""
    try:
        return fn(*args)
    except Exception:
        logger.exception("Attention detector %s failed", name)
        if name not in status["failed"]:
            status["failed"].append(name)
        return []


def _build_raw_rows(company, as_of: date) -> tuple[list[dict], dict]:
    """The expensive, user-independent rows plus which detectors failed or hit a cap."""
    with detector_status() as status:
        raw: list[dict] = []
        raw.extend(_guard("alerts", status, _map_legacy_alerts, company, as_of))
        seen = {r["code"] for r in raw}
        raw.extend(_guard("growth_hints", status, _map_hints, company, as_of, seen))
        raw.extend(_guard(
            "leakage",
            status,
            lambda: build_leakage_detectors(
                company, as_of=as_of, row_factory=_row, rupees_to_paise=rupees_to_paise,
            ),
        ))
        raw.extend(_guard("gst_itc", status, _itc_and_gst_rows, company, as_of))
        raw.extend(_guard("gst_rate_exposure", status, _gst_rate_exposure_rows, company, as_of))
        raw.extend(_guard("irn", status, _irn_rows, company))
        raw.extend(_guard("paid_pending_books", status, _paid_pending_books_rows, company))
        raw.extend(_guard("overdue_customers", status, _overdue_customer_rows, company, as_of))
        raw.extend(_guard("expiry", status, _expiry_rows, company))
        raw.extend(_guard("promise_to_pay", status, _promise_to_pay_rows, company, as_of))
    return raw, {"failed": list(status["failed"]), "truncated": list(status["truncated"])}


_ATTENTION_DEGRADED_TTL = 5


def _build_raw_rows_cached(company, as_of: date) -> tuple[list[dict], dict]:
    cache_key = f"insights:attention_raw:{company.pk}:{as_of.isoformat()}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and "rows" in cached:
        return cached["rows"], cached["status"]
    raw, status = _build_raw_rows(company, as_of)
    # The status is stored with the rows so a cache hit still knows what failed or was capped.
    # A degraded result is kept only briefly: a transient error must not be served for a minute.
    ttl = _ATTENTION_DEGRADED_TTL if status["failed"] else _ATTENTION_RAW_TTL
    cache.set(cache_key, {"rows": raw, "status": status}, ttl)
    return raw, status


def invalidate_attention_cache(company, as_of: date | None = None) -> None:
    invalidate_attention_cache_for(company.pk, as_of)


def invalidate_attention_cache_for(company_id, as_of: date | None = None) -> None:
    try:
        as_of = as_of or timezone.localdate()
        cache.delete(f"insights:attention_raw:{company_id}:{as_of.isoformat()}")
    except Exception:
        pass


def _degraded_row(company, status: dict) -> dict:
    names = ", ".join(sorted(status["failed"]))
    return _row(
        code="FEED_DEGRADED",
        severity="warning",
        title="Some checks could not run",
        money_impact_paise=0,
        reason=f"These checks failed and may be hiding problems: {names}. Reload to retry.",
        action_label="Reload",
        action_href="/attention",
        source_ticket="DAN-05",
        entity_type="company",
        entity_id=company.id,
        dedupe_key=f"FEED_DEGRADED:{company.id}",
        params={"checks": names},
    )


def _collect_rows(company, as_of: date) -> tuple[list[dict], dict]:
    """Every row for the company before dismiss/snooze/visibility, plus detector status."""
    raw, cached_status = _build_raw_rows_cached(company, as_of)
    status = {"failed": list(cached_status["failed"]), "truncated": list(cached_status["truncated"])}

    # Predicted-dunning, customer-action, and residual-return rows must be
    # compute-on-read, not copy Attention's own 60s no-invalidation cache —
    # a paid invoice, a new order, or a newly returned invoice should
    # reflect on the very next load, not up to 60s later. Merge them in
    # after the cached read, not inside it.
    from insights.customer_actions import build_customer_action_rows
    from payments.predictive_dunning import predicted_rows

    with detector_status() as live:
        extra = (
            _guard("predicted_dunning", status, predicted_rows, company, as_of)
            + _guard("customer_actions", status, build_customer_action_rows, company, as_of)
            + _guard("residual_returns", status, _residual_return_rows, company)
        )
    status["failed"].extend(n for n in live["failed"] if n not in status["failed"])
    status["truncated"].extend(c for c in live["truncated"] if c not in status["truncated"])

    rows = _merge_customer_receivables(raw + extra)
    if status["failed"]:
        rows = rows + [_degraded_row(company, status)]
    return rows, status


def build_attention_rows(company, company_user=None, as_of: date | None = None) -> list[dict]:
    """The ranked feed for one person. Read-only: it never writes (DAN-06)."""
    return build_attention_rows_with_status(company, company_user, as_of)[0]


def build_attention_rows_with_status(company, company_user=None, as_of: date | None = None):
    as_of = as_of or timezone.localdate()
    raw, status = _collect_rows(company, as_of)
    ranked = _merge_and_rank(raw)
    visible, states = _apply_state(company, ranked)
    if company_user is not None:
        visible = [r for r in visible if _can_see(company_user, r["code"])]
    seen_at = getattr(company_user, "last_attention_seen_at", None)
    now = timezone.now()
    for row in visible:
        first = _parse_iso(row.get("first_seen"))
        row["age_days"] = max(0, (now - first).days) if first else 0
        row["is_new"] = bool(seen_at and first and first > seen_at)
    contracted = [_contract(r) for r in visible]
    return _attach_assignment(company, contracted, states), status


def _parse_iso(value):
    from django.utils.dateparse import parse_datetime

    if not value:
        return None
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def sweep_attention_state(company, as_of: date | None = None, now=None) -> dict:
    """Persist what a reader of the feed must not write (DAN-06).

    Stores first_seen for new rows, clears expired snoozes, lets a dismissal lapse once its
    condition is really gone, and records resolved outcomes. A detector that failed or hit its
    cap cannot be told apart from "condition gone", so its rows keep their state this round.
    """
    from insights.outcomes import code_for_key, observe_resolved_outcomes

    as_of = as_of or timezone.localdate()
    now = now or timezone.now()
    raw, status = _collect_rows(company, as_of)
    ranked = _merge_and_rank(raw)
    keys = [r["dedupe_key"] for r in ranked]

    known = set(
        AttentionRowState.objects.filter(company=company, dedupe_key__in=keys).values_list("dedupe_key", flat=True)
    )
    created = [
        AttentionRowState(company=company, dedupe_key=key, first_seen=now) for key in keys if key not in known
    ]
    if created:
        AttentionRowState.objects.bulk_create(created, ignore_conflicts=True)

    AttentionRowState.objects.filter(
        company=company, dismissed=False, snooze_until__isnull=False, snooze_until__lte=now,
    ).update(snooze_until=None, snooze_reason="")

    # A set-aside merged row that gained a signal or got worse is shown again; make that stick.
    by_key = {r["dedupe_key"]: r for r in ranked}
    for state in AttentionRowState.objects.filter(company=company, dedupe_key__in=keys).filter(
        Q(dismissed=True) | Q(snooze_until__gt=now)
    ):
        live = by_key.get(state.dedupe_key)
        if live and _escalated(state.signal_fingerprint, live.get("signal_fingerprint", "")):
            state.dismissed = False
            state.snooze_until = None
            state.snooze_reason = ""
            state.signal_fingerprint = live.get("signal_fingerprint", "")
            state.state_at = now
            state.save(update_fields=[
                "dismissed", "snooze_until", "snooze_reason", "signal_fingerprint", "state_at", "updated_at",
            ])

    paused = _paused_codes(status)
    failed = paused is None
    unsure = (
        [
            key
            for key in AttentionRowState.objects.filter(company=company).values_list("dedupe_key", flat=True)
            if code_for_key(key) in paused
        ]
        if paused
        else []
    )

    cleared = 0
    resolved = 0
    if not failed:
        cleared = (
            AttentionRowState.objects.filter(company=company, dismissed=True)
            .exclude(dedupe_key__in=set(keys) | set(unsure))
            .update(dismissed=False, snooze_until=None, snooze_reason="")
        )
        resolved = observe_resolved_outcomes(company, set(keys) | set(unsure), now)
    return {"created": len(created), "cleared": cleared, "resolved": resolved, "failed": status["failed"]}


def _attach_assignment(company, rows: list[dict], states: dict | None = None) -> list[dict]:
    from core.services.feature_flags import flag_enabled

    if not flag_enabled(company, "ENABLE_ACTION_ASSIGNMENT"):
        return rows
    if states is None:
        keys = [row["dedupe_key"] for row in rows]
        states = {
            state.dedupe_key: state
            for state in AttentionRowState.objects.filter(company=company, dedupe_key__in=keys)
        }
    today = timezone.localdate()
    for row in rows:
        state = states.get(row["dedupe_key"])
        assigned_id = state.assigned_to_id if state is not None else None
        due = state.due_date if state is not None else None
        row["assigned_to"] = assigned_id
        row["due_date"] = due.isoformat() if due else None
        row["overdue"] = bool(due and due < today)
    return rows


_UNSET = object()


def _state_view(state) -> dict:
    return {
        "dismissed": bool(state.dismissed),
        "snooze_until": _iso(state.snooze_until),
        "assigned_to": state.assigned_to_id,
        "due_date": state.due_date.isoformat() if state.due_date else None,
    }


def _audit_action(company, company_user, event: str, dedupe_key: str, *, before: dict, state, reason: str = "") -> None:
    """DAN-14: who did what to which row, with the state before and after.

    Written in the same transaction as the change, so there is never a change without its record.
    """
    from core.services.audit import AuditService

    from insights.telemetry import record_event

    # A count for pilot reporting; the audit event below is the record.
    record_event(
        company, "attention_action", user=getattr(company_user, "user", None),
        journey="attention", feature=event, success=True,
    )
    AuditService.log(
        company=company,
        user=getattr(company_user, "user", None),
        action=f"attention.{event}",
        entity_type="AttentionRow",
        entity_id=dedupe_key[:64],
        description=f"attention row {event}"[:240],
        metadata={"dedupe_key": dedupe_key, "reason": reason[:500], "before": before, "after": _state_view(state)},
    )


def _guard_action(company_user, dedupe_key: str, *, action: str) -> str:
    """Server-side rules for dismiss / snooze / assign (DAN-04). Returns the row's code.

    The UI hides buttons, but a direct API call must meet the same rules.
    """
    from core.exceptions import BusinessRuleError

    from insights.outcomes import code_for_key

    if not dedupe_key:
        raise BusinessRuleError("dedupe_key is required.")
    if len(dedupe_key) > 191:
        raise BusinessRuleError("dedupe_key is too long.", code="row_not_actionable")
    code = code_for_key(dedupe_key)
    if code not in KNOWN_CODES:
        raise BusinessRuleError("Unknown item.", code="row_not_actionable")
    if company_user is not None and not _can_see(company_user, code):
        raise BusinessRuleError("You cannot act on this item.", code="row_not_actionable")
    blocked = {"dismiss": NON_DISMISSIBLE, "snooze": NON_SNOOZABLE, "assign": NON_ASSIGNABLE}[action]
    if code in blocked:
        message = {
            "dismiss": "This cannot be dismissed. Fix it, or snooze it.",
            "snooze": "This cannot be snoozed.",
            "assign": "This cannot be assigned.",
        }[action]
        raise BusinessRuleError(message, code="row_not_actionable")
    return code


@transaction.atomic
def assign_attention_row(company, company_user, *, dedupe_key: str, assignee_id=_UNSET, due_date=_UNSET):
    from datetime import date as date_cls
    from datetime import timezone as dt_timezone

    from django.utils.dateparse import parse_datetime

    from accounts.models import CompanyUser
    from core.exceptions import BusinessRuleError
    from core.services.feature_flags import flag_enabled
    from core.services.flag_observability import log_flag_event

    if not flag_enabled(company, "ENABLE_ACTION_ASSIGNMENT"):
        raise BusinessRuleError("Action assignment is off for this company.")
    dedupe_key = (dedupe_key or "").strip()
    code = _guard_action(company_user, dedupe_key, action="assign")
    now = timezone.now()
    state, _created = AttentionRowState.objects.get_or_create(
        company=company,
        dedupe_key=dedupe_key,
        defaults={"first_seen": now},
    )
    # Two people acting on one row at once: take the row lock so the second waits and both
    # changes are audited in order (a no-op on SQLite, real on Postgres).
    state = AttentionRowState.objects.select_for_update().get(pk=state.pk)
    # Only touch a field that was actually provided — omitting one field to
    # update only the other must not silently clear the field left alone.
    before = _state_view(state)
    update_fields = ["updated_by", "updated_at"]
    if assignee_id is not _UNSET:
        assignee = None
        if assignee_id not in (None, "", 0):
            assignee = CompanyUser.objects.filter(
                company=company, pk=assignee_id, user__is_active=True
            ).first()
            if assignee is None:
                raise BusinessRuleError("Assignee must be an active member of this company.")
            if not _can_see(assignee, code):
                raise BusinessRuleError(
                    "That person cannot work on this kind of item.", code="assignee_cannot_act"
                )
        state.assigned_to = assignee
        update_fields.append("assigned_to")
    if due_date is not _UNSET:
        parsed_due = None
        if due_date not in (None, ""):
            if isinstance(due_date, date_cls):
                parsed_due = due_date
            else:
                raw = str(due_date)
                if len(raw) > 10 or "T" in raw:
                    # A full timestamp (e.g. a browser's Date.toISOString(),
                    # always UTC) must be converted to local time before
                    # taking its date — slicing the first 10 characters
                    # assumes the timestamp is already local and can land a
                    # day early for anyone east of UTC.
                    parsed_dt = parse_datetime(raw)
                    if parsed_dt is None:
                        raise BusinessRuleError("due_date must be YYYY-MM-DD.")
                    if timezone.is_naive(parsed_dt):
                        parsed_dt = timezone.make_aware(parsed_dt, dt_timezone.utc)
                    parsed_due = timezone.localtime(parsed_dt).date()
                else:
                    parsed_due = date_cls.fromisoformat(raw)
        state.due_date = parsed_due
        update_fields.append("due_date")
    state.updated_by = getattr(company_user, "user", None)
    state.save(update_fields=update_fields)
    _audit_action(company, company_user, "assigned", dedupe_key, before=before, state=state)
    log_flag_event(company, "ENABLE_ACTION_ASSIGNMENT", "action_assigned", dedupe_key=dedupe_key)
    return {
        "dedupe_key": dedupe_key,
        "assigned_to": state.assigned_to_id,
        "due_date": state.due_date.isoformat() if state.due_date else None,
    }


def _live_row(company, dedupe_key: str):
    """The current row behind a key (after merging), or None when its condition is not live."""
    try:
        rows, _status = _collect_rows(company, timezone.localdate())
    except Exception:
        return None
    for row in rows:
        if row["dedupe_key"] == dedupe_key:
            return row
    return None


SNAPSHOT_KEYS = (
    "code",
    "severity",
    "title",
    "reason",
    "money_impact_paise",
    "currency",
    "action_label",
    "action_href",
    "source_ticket",
    "entity_ref",
    "params",
)


def _snapshot(live, code: str) -> dict:
    if not live:
        return {"code": code}
    return {k: live.get(k) for k in SNAPSHOT_KEYS}


@transaction.atomic
def dismiss_attention_row(company, company_user, *, dedupe_key: str, reason: str = "") -> dict:
    """Hide the row. Dismissal is not approval and does not snooze.

    A possible-duplicate-payment row is a claim that money may have been recorded twice, so
    setting it aside needs a reason, kept with the row. A critical row needs one too.
    """
    from core.exceptions import BusinessRuleError

    from insights.outcomes import record_dismissal

    dedupe_key = (dedupe_key or "").strip()
    code = _guard_action(company_user, dedupe_key, action="dismiss")
    reason = (reason or "").strip()
    live = _live_row(company, dedupe_key)
    severity = live["severity"] if live else None
    # A critical row, or one that claims money may be wrong, is not set aside without saying why.
    if len(reason) < MIN_REASON_LENGTH and (code in REASON_REQUIRED_CODES or severity == "critical"):
        message = (
            "Say why this is not a duplicate (at least 3 characters)."
            if code == "DUPLICATE_PAYMENT"
            else "Say why you are setting this aside (at least 3 characters)."
        )
        raise BusinessRuleError(message, code="dismiss_reason_required")
    now = timezone.now()
    state, _ = AttentionRowState.objects.get_or_create(
        company=company,
        dedupe_key=dedupe_key,
        defaults={"first_seen": now},
    )
    # Two people acting on one row at once: take the row lock so the second waits and both
    # changes are audited in order (a no-op on SQLite, real on Postgres).
    state = AttentionRowState.objects.select_for_update().get(pk=state.pk)
    before = _state_view(state)
    state.dismissed = True
    # Dismissing replaces an earlier snooze: a row is set aside one way or the other, never both.
    state.snooze_until = None
    state.snooze_reason = reason[:2000]
    state.state_at = now
    state.snapshot = _snapshot(live, code)
    state.signal_fingerprint = (live or {}).get("signal_fingerprint", "")
    state.updated_by = getattr(company_user, "user", None)
    state.save(update_fields=[
        "dismissed", "snooze_until", "snooze_reason", "state_at", "snapshot", "signal_fingerprint",
        "updated_by", "updated_at",
    ])
    _audit_action(company, company_user, "dismissed", dedupe_key, before=before, state=state, reason=reason)
    outcome = record_dismissal(company, state, now)
    return {
        "dedupe_key": dedupe_key,
        "dismissed": True,
        "within_window": outcome.within_window,
    }


@transaction.atomic
def snooze_attention_row(company, company_user, *, dedupe_key: str, days: int, reason: str) -> dict:
    from core.exceptions import BusinessRuleError

    reason = (reason or "").strip()
    if not reason:
        raise BusinessRuleError("Snooze requires a reason.")
    dedupe_key = (dedupe_key or "").strip()
    code = _guard_action(company_user, dedupe_key, action="snooze")
    days = max(1, min(int(days or 7), 90))
    now = timezone.now()
    until = now + timedelta(days=days)
    live = _live_row(company, dedupe_key)
    state, _ = AttentionRowState.objects.get_or_create(
        company=company,
        dedupe_key=dedupe_key,
        defaults={"first_seen": now},
    )
    # Two people acting on one row at once: take the row lock so the second waits and both
    # changes are audited in order (a no-op on SQLite, real on Postgres).
    state = AttentionRowState.objects.select_for_update().get(pk=state.pk)
    before = _state_view(state)
    state.snooze_until = until
    state.snooze_reason = reason[:2000]
    state.dismissed = False
    state.state_at = now
    state.snapshot = _snapshot(live, code)
    state.signal_fingerprint = (live or {}).get("signal_fingerprint", "")
    state.updated_by = getattr(company_user, "user", None)
    state.save(update_fields=[
        "snooze_until", "snooze_reason", "dismissed", "state_at", "snapshot", "signal_fingerprint",
        "updated_by", "updated_at",
    ])
    _audit_action(company, company_user, "snoozed", dedupe_key, before=before, state=state, reason=reason)
    return {
        "dedupe_key": dedupe_key,
        "snooze_until": _iso(until),
        "reason": state.snooze_reason,
    }


@transaction.atomic
def reopen_attention_row(company, company_user, *, dedupe_key: str) -> dict:
    """Undo a dismiss or snooze (DAN-09).

    The dismissal outcome is removed: AttentionOutcome is unique per key and a key that already has
    an outcome is never observed again, so a reopened row that is later fixed would otherwise never
    count as resolved, and the dismissal would stay in the learning report.
    """
    from core.exceptions import BusinessRuleError

    from insights.models import AttentionOutcome

    dedupe_key = (dedupe_key or "").strip()
    if not dedupe_key:
        raise BusinessRuleError("dedupe_key is required.")
    state = AttentionRowState.objects.select_for_update().filter(company=company, dedupe_key=dedupe_key).first()
    if state is None or not (state.dismissed or state.snooze_until):
        raise BusinessRuleError("This item is not dismissed or snoozed.", code="row_not_set_aside")
    before = _state_view(state)
    state.dismissed = False
    state.snooze_until = None
    state.snooze_reason = ""
    state.state_at = timezone.now()
    state.updated_by = getattr(company_user, "user", None)
    state.save(update_fields=["dismissed", "snooze_until", "snooze_reason", "state_at", "updated_by", "updated_at"])
    _audit_action(company, company_user, "reopened", dedupe_key, before=before, state=state)
    AttentionOutcome.objects.filter(
        company=company, dedupe_key=dedupe_key, outcome=AttentionOutcome.Outcome.DISMISSED
    ).delete()
    return {"dedupe_key": dedupe_key, "reopened": True}


def mark_attention_seen(company_user) -> dict:
    """The person has looked at the list; rows first seen after this are 'new' next time."""
    now = timezone.now()
    company_user.last_attention_seen_at = now
    company_user.save(update_fields=["last_attention_seen_at", "updated_at"])
    return {"seen_at": _iso(now)}


# --- listing: filters, paging, tabs ---------------------------------------

CATEGORIES = ("money", "gst", "stock", "other")
MONEY_CODES = frozenset({
    "AR_OVERDUE_CRITICAL", "AR_OVERDUE_WARN", "AR_OVERDUE_CUSTOMER", "AR_COLLECTION_RISK", "AR_CUSTOMER",
    "AR_RESIDUAL_AFTER_RETURN", "AP_DUE_7D", "CREDIT_LIMIT_NEAR", "PREDICTED_LATE_PAYMENT",
    "PROMISE_TO_PAY_DUE", "PAID_PENDING_BOOKS", "DUPLICATE_PAYMENT", "WALK_IN_UNALLOCATED_RECEIPT",
    "VOID_RATE_HIGH", "CASH_TIGHT_14D", "OVERDUE_CONCENTRATION",
})
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def category_for(code: str) -> str:
    if code in GST_CODES:
        return "gst"
    if code in STOCK_CODES:
        return "stock"
    if code in MONEY_CODES:
        return "money"
    return "other"


def _count_by(rows: list[dict], key) -> dict:
    out: dict = {}
    for row in rows:
        k = key(row)
        out[k] = out.get(k, 0) + 1
    return out


def build_attention_feed(
    company,
    company_user=None,
    *,
    severity: str = "",
    category: str = "",
    assigned: str = "",
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> dict:
    """The open list with filters and paging, plus counts that ignore the filters."""
    rows, status = build_attention_rows_with_status(company, company_user=company_user)
    degraded = [r for r in rows if r["code"] == "FEED_DEGRADED"]
    counts_by_severity = _count_by(rows, lambda r: r["severity"])
    counts_by_category = _count_by(rows, lambda r: category_for(r["code"]))

    filtered = rows
    if severity in SEVERITY_RANK:
        filtered = [r for r in filtered if r["severity"] == severity]
    if category in CATEGORIES:
        filtered = [r for r in filtered if category_for(r["code"]) == category]
    if assigned == "mine" and company_user is not None:
        filtered = [r for r in filtered if r.get("assigned_to") == company_user.id]
    elif assigned == "unassigned":
        filtered = [r for r in filtered if not r.get("assigned_to")]

    limit = max(1, min(int(limit or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    offset = max(0, int(offset or 0))
    page = filtered[offset: offset + limit]
    next_offset = offset + limit if offset + limit < len(filtered) else None
    return {
        "rows": page,
        "count": len(filtered),
        "total_count": len(rows),
        "critical_count": counts_by_severity.get("critical", 0),
        "counts_by_severity": counts_by_severity,
        "counts_by_category": counts_by_category,
        "next_offset": next_offset,
        "degraded": bool(degraded),
        # Lists a check cut short: these codes may have more items than shown.
        "truncated_codes": sorted(status["truncated"]),
        "as_of": _iso(timezone.now()),
    }


def list_set_aside_rows(company, company_user=None, *, status: str = "snoozed") -> list[dict]:
    """The Snoozed or Dismissed list, from stored state, so a row is still shown after its
    condition has gone. ``condition_cleared`` says whether the problem is still live."""
    now = timezone.now()
    states = AttentionRowState.objects.filter(company=company)
    if status == "dismissed":
        states = states.filter(dismissed=True)
    else:
        states = states.filter(dismissed=False, snooze_until__gt=now)
    states = list(states.select_related("updated_by").order_by("-state_at", "-updated_at")[:200])

    live_keys = None
    try:
        live_rows, live_status = _collect_rows(company, timezone.localdate())
        if not live_status["failed"]:
            live_keys = {r["dedupe_key"] for r in live_rows}
    except Exception:
        live_keys = None

    from insights.outcomes import code_for_key

    out = []
    for state in states:
        code = (state.snapshot or {}).get("code") or code_for_key(state.dedupe_key)
        if company_user is not None and not _can_see(company_user, code):
            continue
        snap = state.snapshot or {}
        user = state.updated_by
        row = {
            "code": code,
            "severity": snap.get("severity") or "info",
            "title": snap.get("title") or code.replace("_", " ").title(),
            "money_impact_paise": int(snap.get("money_impact_paise") or 0),
            "currency": snap.get("currency") or "INR",
            "reason": snap.get("reason") or "",
            "action_label": snap.get("action_label") or "Open",
            "action_href": snap.get("action_href") or fallback_href(code),
            "source_ticket": snap.get("source_ticket") or "",
            "params": snap.get("params") or {},
            "entity_ref": snap.get("entity_ref") or {"type": "company", "id": company.id},
            "dedupe_key": state.dedupe_key,
            "first_seen": _iso(state.first_seen),
            "snooze_until": _iso(state.snooze_until) if status != "dismissed" else None,
            "state": "dismissed" if status == "dismissed" else "snoozed",
            "state_by": (
                {"user_id": user.pk, "name": (getattr(user, "full_name", "") or user.email or "").strip()} if user else None
            ),
            "state_at": _iso(state.state_at or state.updated_at),
            "state_reason": state.snooze_reason or "",
            "condition_cleared": None if live_keys is None else state.dedupe_key not in live_keys,
        }
        out.append(_contract(row) | {"condition_cleared": row["condition_cleared"]})
    return out
