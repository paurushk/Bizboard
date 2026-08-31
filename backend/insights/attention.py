"""B-05 Business Attention Center — one ranked feed, frozen AttentionRow contract.

Downstream waves (M/Q/R) must emit this shape only. No LLM.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.utils import timezone

from .alerts import build_business_alerts, build_leakage_detectors
from .models import AttentionRowState
from .services import build_growth_hints

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
)

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

# Codes a cashier / sales staff must not see (margin / leakage / GST money).
FINANCIAL_CODES = frozenset({
    "AR_OVERDUE_CRITICAL",
    "AR_OVERDUE_WARN",
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

_TWOPLACES = Decimal("0.01")


def rupees_to_paise(amount) -> int:
    value = Decimal(str(amount or 0)).quantize(_TWOPLACES, rounding=ROUND_HALF_UP)
    return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


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
        "action_href": action_href or "/",
        "source_ticket": source_ticket,
        "entity_ref": {"type": entity_type, "id": int(entity_id)},
        "dedupe_key": key,
        "first_seen": None,
        "snooze_until": None,
    }


def _contract(row: dict) -> dict:
    return {k: row[k] for k in ATTENTION_ROW_KEYS}


def _can_see(company_user, code: str) -> bool:
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
    if code in {"PAID_PENDING_BOOKS", "DUPLICATE_PAYMENT"}:
        return bool(company_user.can_create_payments or company_user.can_view_financial_reports)
    if code in {"NO_SALES_TODAY", "AR_OVERDUE_CUSTOMER"}:
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
        href = raw.get("cta_path") or "/"
        out.append(_row(
            code=code,
            severity=raw.get("severity") or "info",
            title=raw.get("message") or code,
            money_impact_paise=_paise_from_legacy_alert(raw),
            reason=raw.get("message") or code,
            action_label="Fix",
            action_href=href,
            source_ticket="B-05",
            entity_type=doc_type,
            entity_id=int(doc_id),
            dedupe_key=f"{code}:{raw.get('subject_key') or f'{doc_type}:{doc_id}'}",
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
            action_href=hint.get("cta_path") or "/",
            source_ticket="B-05",
            entity_type="company",
            entity_id=company.id,
            dedupe_key=f"{code}:hint:{company.id}",
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
            ))
    try:
        gst = build_gst_health(company)
    except Exception:
        return rows
    for alert in (gst.get("alerts") or [])[:25]:
        if alert.get("severity") != "critical":
            continue
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
        action_label="Open rate back-scan",
        action_href="/reports/gst-rate-exposure",
        source_ticket="B-06",
        entity_type="company",
        entity_id=company.id,
        dedupe_key=f"GST_RATE_EXPOSURE:{company.id}",
    )]


def _irn_rows(company) -> list[dict]:
    from sales.models import SalesInvoice

    rows = []
    qs = SalesInvoice.objects.filter(
        company=company,
        status=SalesInvoice.Status.COMPLETED,
        einvoice_status=SalesInvoice.EInvoiceStatus.FAILED,
    ).only("id", "number", "grand_total")[:20]
    for inv in qs:
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
        ))
    return rows


def _paid_pending_books_rows(company) -> list[dict]:
    from payments.models import GatewayPayment, GatewayPaymentStatus, PaymentLink, PaymentLinkStatus

    rows = []
    links = PaymentLink.objects.filter(
        company=company,
        status=PaymentLinkStatus.PAID,
        paid_receipt__isnull=True,
    ).only("id", "amount")[:20]
    for link in links:
        rows.append(_row(
            code="PAID_PENDING_BOOKS",
            severity="critical",
            title="Gateway paid — receipt not posted",
            money_impact_paise=rupees_to_paise(link.amount),
            reason="A payment link is PAID but no customer receipt is linked.",
            action_label="Post receipt",
            action_href="/sales/receipts",
            source_ticket="W0-03",
            entity_type="payment_link",
            entity_id=link.id,
        ))
    captured = (
        GatewayPayment.objects.filter(
            company=company,
            status__in=(
                GatewayPaymentStatus.CAPTURED,
                GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
            ),
            receipts__isnull=True,
        )
        .distinct()
        .only("id", "amount", "status")[:20]
    )
    for gp in captured:
        rows.append(_row(
            code="PAID_PENDING_BOOKS",
            severity="critical",
            title="Captured payment with no receipt",
            money_impact_paise=rupees_to_paise(gp.amount),
            reason="Gateway capture has no linked customer receipt.",
            action_label="Post receipt",
            action_href="/sales/receipts",
            source_ticket="W0-03",
            entity_type="gateway_payment",
            entity_id=gp.id,
        ))
    return rows


def _overdue_customer_rows(company, as_of: date) -> list[dict]:
    from masters.models import Customer
    from payments.dunning import customer_risk_snapshot
    from sales.models import SalesInvoice

    rows = []
    cutoff = as_of - timedelta(days=1)
    cust_ids = (
        SalesInvoice.objects.filter(
            company=company,
            status=SalesInvoice.Status.COMPLETED,
            due_date__lte=cutoff,
        )
        .values_list("customer_id", flat=True)
        .distinct()[:30]
    )
    for cid in cust_ids:
        cust = Customer.objects.filter(company=company, pk=cid).first()
        if not cust:
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
            action_href=f"/sales/customers",
            source_ticket="A-07",
            entity_type="customer",
            entity_id=cust.id,
        ))
    return rows


def _expiry_rows(company) -> list[dict]:
    from inventory.item_stock import expiry_horizon_rows

    rows = []
    try:
        horizon = expiry_horizon_rows(company, days=30)
    except Exception:
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
        ))
        if len(rows) >= 15:
            break
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


def _apply_state(company, ranked: list[dict]) -> list[dict]:
    now = timezone.now()
    keys = [r["dedupe_key"] for r in ranked]
    existing = {
        s.dedupe_key: s
        for s in AttentionRowState.objects.filter(company=company, dedupe_key__in=keys)
    }
    # Condition gone → clear dismiss so a later return reappears.
    AttentionRowState.objects.filter(company=company, dismissed=True).exclude(
        dedupe_key__in=keys,
    ).update(dismissed=False, snooze_until=None, snooze_reason="")

    visible = []
    to_create = []
    for row in ranked:
        state = existing.get(row["dedupe_key"])
        if state is None:
            to_create.append(
                AttentionRowState(
                    company=company,
                    dedupe_key=row["dedupe_key"],
                    first_seen=now,
                )
            )
            row["first_seen"] = _iso(now)
            row["snooze_until"] = None
            visible.append(row)
            continue
        if state.dismissed:
            continue
        if state.snooze_until and state.snooze_until > now:
            continue
        if state.snooze_until and state.snooze_until <= now:
            state.snooze_until = None
            state.snooze_reason = ""
            state.save(update_fields=["snooze_until", "snooze_reason", "updated_at"])
        row["first_seen"] = _iso(state.first_seen)
        row["snooze_until"] = None
        visible.append(row)

    if to_create:
        AttentionRowState.objects.bulk_create(to_create, ignore_conflicts=True)
    return visible


def build_attention_rows(company, company_user=None, as_of: date | None = None) -> list[dict]:
    as_of = as_of or timezone.localdate()
    raw: list[dict] = []
    raw.extend(_map_legacy_alerts(company, as_of))
    seen = {r["code"] for r in raw}
    raw.extend(_map_hints(company, as_of, seen))
    raw.extend(build_leakage_detectors(company, as_of=as_of, row_factory=_row, rupees_to_paise=rupees_to_paise))
    raw.extend(_itc_and_gst_rows(company, as_of))
    raw.extend(_gst_rate_exposure_rows(company, as_of))
    raw.extend(_irn_rows(company))
    raw.extend(_paid_pending_books_rows(company))
    raw.extend(_overdue_customer_rows(company, as_of))
    raw.extend(_expiry_rows(company))

    ranked = _merge_and_rank(raw)
    visible = _apply_state(company, ranked)
    if company_user is not None:
        visible = [r for r in visible if _can_see(company_user, r["code"])]
    return [_contract(r) for r in visible]


def snooze_attention_row(company, company_user, *, dedupe_key: str, days: int, reason: str) -> dict:
    reason = (reason or "").strip()
    if not reason:
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("Snooze requires a reason.")
    days = max(1, min(int(days or 7), 90))
    now = timezone.now()
    until = now + timedelta(days=days)
    state, _ = AttentionRowState.objects.get_or_create(
        company=company,
        dedupe_key=dedupe_key,
        defaults={"first_seen": now},
    )
    state.snooze_until = until
    state.snooze_reason = reason[:2000]
    state.dismissed = False
    state.updated_by = getattr(company_user, "user", None)
    state.save(update_fields=["snooze_until", "snooze_reason", "dismissed", "updated_by", "updated_at"])
    return {
        "dedupe_key": dedupe_key,
        "snooze_until": _iso(until),
        "reason": state.snooze_reason,
    }
