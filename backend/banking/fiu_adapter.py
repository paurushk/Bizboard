"""FIU adapter for Account Aggregator ingest.

Mock path is allowlisted in views (dev/test/local only). Live HTTP is fail-closed
without FIU_BASE_URL and never invents rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone


@dataclass
class MockFiTransaction:
    txn_id: str
    amount: Decimal
    txn_date: date
    narration: str
    raw: dict[str, Any]


def fetch_transactions_for_consent(*, consent_id: str, fi_type: str) -> list[MockFiTransaction]:
    """Return deterministic mock transactions for local/dev AA ingest."""
    suffix = consent_id[-4:] if consent_id else "0000"
    return [
        MockFiTransaction(
            txn_id=f"aa-mock-{suffix}-001",
            amount=Decimal("1500.00"),
            txn_date=timezone.localdate(),
            narration="UPI/CR/MOCK CUSTOMER",
            raw={"mode": "UPI", "fi_type": fi_type, "consent_id": consent_id},
        ),
        MockFiTransaction(
            txn_id=f"aa-mock-{suffix}-002",
            amount=Decimal("2500.50"),
            txn_date=timezone.localdate(),
            narration="NEFT/CR/MOCK CUSTOMER",
            raw={"mode": "NEFT", "fi_type": fi_type, "consent_id": consent_id},
        ),
    ]


def fetch_live_transactions_for_consent(*, consent_id: str, fi_type: str) -> list[MockFiTransaction]:
    """HTTP FIU fetch. Raises BusinessRuleError when unset or the FIU fails."""
    import json
    import urllib.error
    import urllib.request

    from django.conf import settings

    from core.exceptions import BusinessRuleError

    base = (getattr(settings, "FIU_BASE_URL", "") or "").rstrip("/")
    if not base:
        raise BusinessRuleError("Live AA ingest is fail-closed: FIU_BASE_URL is not configured.")
    try:
        req = urllib.request.Request(
            f"{base}/consents/{consent_id}/transactions?fi_type={fi_type}",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        raise BusinessRuleError("Live AA FIU fetch failed closed.") from exc

    rows = payload.get("transactions") or payload.get("data") or []
    out: list[MockFiTransaction] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        txn_id = str(row.get("txn_id") or row.get("id") or "").strip()
        if not txn_id:
            continue
        txn_date = timezone.localdate()
        raw_date = str(row.get("txn_date") or row.get("date") or "")
        if raw_date:
            try:
                txn_date = date.fromisoformat(raw_date[:10])
            except ValueError:
                pass
        out.append(
            MockFiTransaction(
                txn_id=txn_id,
                amount=Decimal(str(row.get("amount") or "0")),
                txn_date=txn_date,
                narration=str(row.get("narration") or ""),
                raw={"fi_type": fi_type, "consent_id": consent_id, **row},
            )
        )
    return out
