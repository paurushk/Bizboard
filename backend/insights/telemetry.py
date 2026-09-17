"""SR-52 / D-pilot — server-side pilot telemetry emit points.

Companion to the FE `ShopFloorEvent` ingest (`insights/views.py`). These are
first-party, PII-free counters used to score the pilot hypotheses
(BUSINESS_ARCHETYPES_AND_PERSONAS.md section 11) without hand-tallying:

  * H-01  allocation_reconciled  — one per payment allocation; tap_count 1 flags
          a derived-ledger discrepancy.
  * H-03  offline_flush_fail / offline_enqueue — FE-emitted, already wired.
  * period_closed — month-end cadence marker.
  * signup_completed / wizard_tax_confirmed / wizard_completed — 15.3 funnel.

Emission never raises: a telemetry failure must not break a money path.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("insights.telemetry")


def record_event(
    company,
    event: str,
    *,
    duration_ms=None,
    tap_count=None,
    user=None,
    journey="",
    feature="",
    role="",
    session_id="",
    request_id="",
    success=None,
    failure_reason="",
) -> None:
    try:
        from django.utils import timezone

        from core.observability import current_request_id

        from .models import ShopFloorEvent

        ShopFloorEvent.objects.create(
            company=company,
            event=event,
            duration_ms=duration_ms,
            tap_count=tap_count,
            occurred_on=timezone.localdate(),
            journey=journey or "",
            feature=feature or "",
            role=(role or "")[:16],
            session_id=(session_id or "")[:36],
            request_id=(request_id or current_request_id() or "")[:64],
            success=success,
            failure_reason=failure_reason or "",
            created_by=user,
            updated_by=user,
        )
    except Exception:  # noqa: BLE001 — telemetry is best-effort
        logger.debug("telemetry emit failed for %s", event, exc_info=True)


def record_allocation_reconciled(sales_invoice, *, user=None) -> None:
    """H-01: emit after a receipt allocation. Flags the invoice if its derived
    outstanding has left the sane band [0, grand_total]."""
    try:
        from decimal import Decimal

        from ledgers.services import LedgerService

        outstanding = LedgerService.sales_invoice_outstanding(sales_invoice)
        grand = Decimal(str(getattr(sales_invoice, "grand_total", 0) or 0))
        discrepancy = 1 if (outstanding < Decimal("0") or outstanding > grand) else 0
        record_event(
            sales_invoice.company,
            "allocation_reconciled",
            tap_count=discrepancy,
            user=user,
            journey="payment",
            success=True,
        )
    except Exception:  # noqa: BLE001
        logger.debug("allocation_reconciled telemetry failed", exc_info=True)


def record_journey_started(company, journey: str, *, user=None, feature="") -> None:
    record_event(company, "journey_started", journey=journey, feature=feature, user=user)


def record_journey_failed(
    company, journey: str, reason: str, *, user=None, feature=""
) -> None:
    record_event(
        company,
        "journey_failed",
        journey=journey,
        feature=feature,
        failure_reason=reason,
        success=False,
        user=user,
    )


def record_pdf_started(company, *, user=None) -> None:
    record_journey_started(company, "pdf", user=user)


def record_pdf_failed(company, *, user=None) -> None:
    record_journey_failed(company, "pdf", "unknown", user=user)
